#!/usr/bin/env bash
# local-wiki.sh: a throwaway MediaWiki in the cloud workspace, to preview the wiki before (or besides)
# the real one. MediaWiki 1.39 from Ubuntu 24.04, skin Vector 2022, SimpleMathJax 0.8.12 + MathJax 3.2.2
# (self-hosted). Part of the wiki kit (2026); drafted by Claude (AI).
#
#   bash local-wiki.sh install "Site name (preview)"   packages, extensions, MathJax (about a minute)
#   bash local-wiki.sh load site.xml                   fresh database, import, purge (server must run)
#   bash local-wiki.sh start | stop | status           php -S on 127.0.0.1:$PORT (default 8080)
#
# "load" always starts from an empty database, so each page has exactly the imported revision.
# The server is a background process: start it in the same turn as the export, it does not survive
# long pauses. Math: <math> without display= is wrapped in \displaystyle, as Miraheze renders it.
set -euo pipefail
MW=/usr/share/mediawiki
DATA=/var/lib/mediawiki/data
CONF=/etc/mediawiki/LocalSettings.php
PORT="${PORT:-8080}"
HOST="http://127.0.0.1:${PORT}"
STATE=/var/lib/mediawiki/kit-sitename
LOG=/tmp/local-wiki-server.log

need_root() { [ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }; }

write_settings() {
  local sitename="$1" pass
  pass="$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 20)Aa1!"
  rm -rf "$DATA" /var/lib/mediawiki/LocalSettings.php.kit "$CONF"
  mkdir -p "$DATA"
  php "$MW/maintenance/install.php" --dbtype=sqlite --dbpath="$DATA" --dbname=kitwiki \
    --server="$HOST" --scriptpath= --lang=en --pass="$pass" --confpath=/var/lib/mediawiki \
    --skins=Vector "$sitename" Admin >/tmp/local-wiki-install.log 2>&1 || { tail -20 /tmp/local-wiki-install.log; exit 1; }
  # install.php writes /var/lib/mediawiki/LocalSettings.php, which is a symlink to $CONF
  cat >> "$CONF" <<'PHP'

# ---- wiki kit preview settings
$wgDefaultSkin = "vector-2022";
$wgMainCacheType = CACHE_DB;
$wgParserCacheType = CACHE_DB;
wfLoadExtension( 'ParserFunctions' );
wfLoadExtension( 'WikiEditor' );
wfLoadExtension( 'Cite' );
wfLoadExtension( 'SimpleMathJax' );
$wgSmjUseCdn = false;
$wgSmjEnableMenu = false;
$wgSmjEnableHtmlAttributes = true;
$wgSmjWrapDisplaystyle = true;      // like Miraheze: <math> without display= is set in display style
$wgSmjDisplayAlign = "center";
$wgSmjUseChem = false;
$wgUseSiteCss = true;
$wgUseSiteJs = true;
$wgAllowSiteCSSOnRestrictedPages = true;
$wgFragmentMode = [ 'html5' ];
$wgUseInstantCommons = false;
$wgVectorDefaultSidebarVisibleForAnonymousUser = true;
$wgDefaultUserOptions['usebetatoolbar'] = 1;
$wgRightsUrl = "https://creativecommons.org/licenses/by/4.0/";
$wgRightsText = "Creative Commons Attribution 4.0";
$wgEnableUploads = false;
$wgShowExceptionDetails = true;
PHP
  chown -R www-data:www-data "$DATA" 2>/dev/null || true
  chmod -R a+rwX "$DATA"
}

case "${1:-}" in
  install)
    need_root
    sitename="${2:-Wiki (preview)}"
    echo "$sitename" > "$STATE"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null
    apt-get install -y -qq --no-install-recommends mediawiki php-sqlite3 php-intl php-mbstring php-xml php-apcu >/tmp/local-wiki-apt.log 2>&1
    ext="$MW/extensions/SimpleMathJax"
    if [ ! -d "$ext" ]; then
      git clone -q --depth 1 --branch v0.8.12 https://github.com/jmnote/SimpleMathJax.git "$ext" 2>/dev/null
      # MediaWiki 1.39 has only the global Html and Sanitizer classes
      sed -i '/^use MediaWiki\\Html\\Html;/d; /^use MediaWiki\\Parser\\Sanitizer;/d' "$ext/SimpleMathJaxHooks.php"
      tmp="$(mktemp -d)"; (cd "$tmp" && npm pack -s mathjax@3.2.2 >/dev/null && tar xzf mathjax-3.2.2.tgz)
      mkdir -p "$ext/resources/MathJax"; cp -r "$tmp/package/es5" "$ext/resources/MathJax/es5"; rm -rf "$tmp"
    fi
    write_settings "$sitename"
    echo "installed: $(php "$MW/maintenance/version.php" 2>/dev/null | cut -d'(' -f1), site \"$sitename\""
    ;;
  start)
    if curl -s -o /dev/null "$HOST/api.php"; then echo "already running at $HOST"; exit 0; fi
    PHP_CLI_SERVER_WORKERS=6 nohup php -S "127.0.0.1:${PORT}" -t "$MW" >"$LOG" 2>&1 &
    for i in $(seq 1 50); do curl -s -o /dev/null "$HOST/api.php" && { echo "running at $HOST"; exit 0; }; sleep 0.2; done
    echo "server did not start; see $LOG" >&2; exit 1
    ;;
  stop)
    pkill -f "[p]hp -S 127.0.0.1:${PORT}" && echo stopped || echo "not running"
    ;;
  status)
    curl -s "$HOST/api.php?action=query&meta=siteinfo&format=json" | head -c 300; echo
    ;;
  load)
    need_root
    xml="${2:?usage: local-wiki.sh load site.xml}"
    write_settings "$(cat "$STATE" 2>/dev/null || echo 'Wiki (preview)')"
    # the installer's Main Page would be newer than the imported one: remove it first
    echo "Main Page" | php "$MW/maintenance/deleteBatch.php" -r "replaced by the kit" >/dev/null 2>&1 || true
    # the contributors named in the XML become local users, so that the histories show their names
    while IFS= read -r u; do
      [ -n "$u" ] && php "$MW/maintenance/createAndPromote.php" "$u" "$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')Aa1!" >/dev/null 2>&1 || true
    done < <(grep -o '<username>[^<]*</username>' "$xml" | sed 's/<[^>]*>//g' | sort -u)
    php "$MW/maintenance/importDump.php" --no-updates < "$xml" 2>&1 | grep -v 'rebuildrecentchanges\|initSiteStats' | tail -2 || true
    php "$MW/maintenance/rebuildrecentchanges.php" >/dev/null 2>&1 || true
    php "$MW/maintenance/refreshLinks.php" >/dev/null 2>&1 || true
    chmod -R a+rwX "$DATA"
    if curl -s -o /dev/null "$HOST/api.php"; then
      for ns in 0 1 4 8 10 12; do
        curl -s -o /dev/null --data "action=purge&generator=allpages&gapnamespace=${ns}&gaplimit=max&forcelinkupdate=1&format=json" "$HOST/api.php"
      done
      echo "purged (forcelinkupdate)"
    else
      echo "server not running: start it, then run load again (or purge by hand), or links may stay red"
    fi
    ;;
  *)
    sed -n '2,13p' "$0"; exit 2 ;;
esac

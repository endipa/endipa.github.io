#!/usr/bin/env python3
"""A vortex in the plane is a shear flow in log-polar coordinates: a figure and a video.

In the plane, with polar coordinates (r, theta), the circular flow u = r V(r) e_theta gives

    d_t f + V(r) d_theta f = nu Delta f.

With r = e^s, that is X + iY = e^{s + i theta}, the plane without the origin becomes the strip
(theta, s) in T x R, and the equation becomes

    d_t f + V(e^s) d_theta f = nu e^{-2s} (d_theta^2 + d_s^2) f,

a shear flow with profile V(e^s) and a variable diffusion coefficient. Here
V(r) = 1 / (1 + r^2), whose profile V(e^s) = 1 / (1 + e^{2s}) has its inflection point
at s = 0 (r = 1), with slope -1/2 there.

Figure (log-polar-map.png, .svg): the polar grid, two annuli of the same width, and a ray carried
by the flow for a time tau, in the plane and in the strip. Nothing is computed numerically: the ray
theta = theta_0 becomes the curve theta = theta_0 + tau V(r).

Video (log-polar.mp4): the datum f_0 = cos(k theta) chi(s), chi(s) = exp(-(s / 0.8)^4), is a single
Fourier mode in theta, so f = Re(g(t, s) e^{i k theta}) with

    e^{2s} d_t g = -i k V(e^s) e^{2s} g + nu (d_s^2 - k^2) g,     g = 0 at the ends of [s_min, s_max],

solved with centred second-order differences in s and the Crank-Nicolson scheme in time. The video
shows f in the plane and in the strip. The norm used in the checks (not shown in the video) is the
L^2 norm in the plane, ||f||^2 = (1/2) int |g|^2 e^{2s} ds (times 2 pi), divided by its initial value;
the same is computed without the flow (V = 0).

Checks (log-polar-check.txt, log-polar-check.png):
  * the run is repeated with twice the points in s and half the time step, and the norms are compared;
  * energy balance: ||f(t)||^2 + 2 nu int_0^t int (|d_s g|^2 + k^2 |g|^2) ds dt' = ||f(0)||^2.

Needs NumPy, SciPy, Matplotlib and ffmpeg (with the libx264 encoder).
Run:  python3 log_polar.py --out ../../wiki/media

Drafted by Claude (AI) on 10 November 2026 for the wiki "Enhanced dissipation for passive
scalars"; record: page Numerical methods, section num-log-polar.
"""
import argparse
import os
import shutil
import subprocess
import tempfile

import numpy as np
from scipy.linalg import solve_banded
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Wedge, Rectangle, FancyArrowPatch

BLUE = "#1f4e79"      # the wiki's primary colour (shear flow in the other videos)
RUST = "#b4532a"      # the wiki's warm colour (heat equation in the other videos)
INK = "#1c222b"       # body text of the wiki
GREY = "#59616e"
GRID = "#c8cfd9"

if any(f.name == "Inter" for f in font_manager.fontManager.ttflist):
    plt.rcParams["font.family"] = ["Inter", "DejaVu Sans"]
plt.rcParams["text.color"] = INK
plt.rcParams["axes.labelcolor"] = INK
plt.rcParams["xtick.color"] = INK
plt.rcParams["ytick.color"] = INK
plt.rcParams["axes.edgecolor"] = INK
plt.rcParams["svg.fonttype"] = "path"     # text as outlines: the picture does not depend on the fonts of the reader


def omega(r):
    return 1.0 / (1.0 + r ** 2)


# ------------------------------------------------------------------------------------------ figure

def draw_map(out):
    s_lo, s_hi = -1.8, 1.1                      # the part of the strip that is shown
    s_grid = np.arange(-1.5, 1.01, 0.5)         # circles r = e^s  <->  horizontal lines
    th_grid = np.arange(12) * np.pi / 6         # rays  <->  vertical lines
    annuli = [((0.28, 0.48), RUST), ((2.0, 2.2), BLUE)]   # the same width in r
    th0, tau = 0.25 * np.pi, 2.5                # the ray theta = th0, carried for a time tau
    R = np.exp(s_hi)

    side, gap, left, bottom, top = 3.0, 1.3, 0.36, 0.72, 0.5
    wide = side * 2 * np.pi / (s_hi - s_lo)     # equal scales in theta and s: the map is conformal
    W, H = left + side + gap + wide + 0.95, bottom + side + top
    fig = plt.figure(figsize=(W, H), dpi=200)
    ax = fig.add_axes([left / W, bottom / H, side / W, side / H])
    bx = fig.add_axes([(left + side + gap) / W, bottom / H, wide / W, side / H])

    # the plane
    t = np.linspace(0, 2 * np.pi, 400)
    for s in s_grid:
        ax.plot(np.exp(s) * np.cos(t), np.exp(s) * np.sin(t), color=GRID, lw=0.8, zorder=1)
    for th in th_grid:
        rr = np.array([np.exp(s_lo), R])
        ax.plot(rr * np.cos(th), rr * np.sin(th), color=GRID, lw=0.8, zorder=1)
    ax.plot(R * np.cos(t), R * np.sin(t), color=GREY, lw=0.9, ls=(0, (4, 3)), zorder=1)
    ax.plot(np.exp(s_lo) * np.cos(t), np.exp(s_lo) * np.sin(t), color=GREY, lw=0.9, ls=(0, (4, 3)), zorder=1)
    for (r1, r2), c in annuli:
        ax.add_patch(Wedge((0, 0), r2, 0, 360, width=r2 - r1, facecolor=c, alpha=0.3, edgecolor="none", zorder=2))
        for r in (r1, r2):
            ax.plot(r * np.cos(t), r * np.sin(t), color=c, lw=1.1, zorder=3)
    rr = np.exp(np.linspace(s_lo, s_hi, 400))
    ax.plot(rr * np.cos(th0), rr * np.sin(th0), color=INK, lw=1.3, ls=(0, (4, 2.5)), zorder=4)
    th1 = th0 + tau * omega(rr)
    ax.plot(rr * np.cos(th1), rr * np.sin(th1), color=INK, lw=1.9, zorder=5)
    for s in np.arange(-1.5, 1.01, 0.5):        # how far each circle turns in the time tau
        r = np.exp(s)
        a = np.linspace(th0, th0 + tau * omega(r), 60)
        ax.plot(r * np.cos(a[:-3]), r * np.sin(a[:-3]), color=INK, lw=0.9, zorder=5)
        ax.add_patch(FancyArrowPatch((r * np.cos(a[-6]), r * np.sin(a[-6])), (r * np.cos(a[-1]), r * np.sin(a[-1])),
                                     arrowstyle="-|>", mutation_scale=7, color=INK, lw=0, shrinkA=0, shrinkB=0, zorder=6))
    ax.text(1.0 * np.cos(-0.5), 1.0 * np.sin(-0.5) - 0.02, "$r=1$", fontsize=8.5, color=GREY, ha="left", va="top")
    ax.set_xlim(-R * 1.03, R * 1.03); ax.set_ylim(-R * 1.03, R * 1.03)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(r"The plane without the origin,  $(X,Y)$", fontsize=11.5, pad=9)

    # the strip
    for s in s_grid:
        bx.plot([0, 2 * np.pi], [s, s], color=GRID, lw=0.8, zorder=1)
    for th in th_grid[1:]:
        bx.plot([th, th], [s_lo, s_hi], color=GRID, lw=0.8, zorder=1)
    for (r1, r2), c in annuli:
        bx.add_patch(Rectangle((0, np.log(r1)), 2 * np.pi, np.log(r2 / r1), facecolor=c, alpha=0.3, edgecolor="none", zorder=2))
        for r in (r1, r2):
            bx.plot([0, 2 * np.pi], [np.log(r)] * 2, color=c, lw=1.1, zorder=3)
    ss = np.log(rr)
    bx.plot([th0, th0], [s_lo, s_hi], color=INK, lw=1.3, ls=(0, (4, 2.5)), zorder=4)
    bx.plot(th1, ss, color=INK, lw=1.9, zorder=5)
    for s in np.arange(-1.5, 1.01, 0.5):
        bx.annotate("", xy=(th0 + tau * omega(np.exp(s)), s), xytext=(th0, s), zorder=6,
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.9, mutation_scale=7, shrinkA=0, shrinkB=0))
    for th in (0, 2 * np.pi):                   # the two sides are the same ray
        bx.plot([th, th], [s_lo, s_hi], color=GREY, lw=0.9, ls=(0, (2, 2)), zorder=1)
    for s in (s_lo, s_hi):
        bx.plot([0, 2 * np.pi], [s, s], color=GREY, lw=0.9, ls=(0, (4, 3)), zorder=1)
    bx.set_xlim(-0.02, 2 * np.pi + 0.02); bx.set_ylim(s_lo - 0.01, s_hi + 0.01)
    bx.set_aspect("equal")
    for sp in bx.spines.values():
        sp.set_visible(False)
    bx.set_xticks([0, np.pi / 2, np.pi, 3 * np.pi / 2, 2 * np.pi])
    bx.set_xticklabels(["0", r"$\pi/2$", r"$\pi$", r"$3\pi/2$", r"$2\pi$"], fontsize=9.5)
    bx.yaxis.tick_right()
    bx.set_yticks([-1, 0, 1]); bx.set_yticklabels(["$-1$", "$0$", "$1$"], fontsize=9.5)
    bx.tick_params(length=3, width=0.8)
    bx.set_xlabel(r"$\theta$", fontsize=11, labelpad=1)
    bx.text(2 * np.pi + 0.5, 0.5 * (s_lo + s_hi), r"$s=\log r$", fontsize=11, rotation=90, va="center", ha="center")
    bx.set_title(r"Log-polar coordinates,  $(\theta,s)\in\mathbb{T}\times\mathbb{R}$", fontsize=11.5, pad=9)

    # the map
    xm, ym = (left + side + gap / 2) / W, (bottom + side / 2) / H
    fig.patches.append(FancyArrowPatch((xm - 0.42 * gap / W, ym), (xm + 0.42 * gap / W, ym), transform=fig.transFigure,
                                       arrowstyle="-|>", mutation_scale=13, color=BLUE, lw=1.6))
    fig.text(xm, ym + 0.085, r"$X=e^{s}\cos\theta$", ha="center", va="bottom", fontsize=10)
    fig.text(xm, ym + 0.03, r"$Y=e^{s}\sin\theta$", ha="center", va="bottom", fontsize=10)
    handles = [Line2D([], [], color=INK, lw=1.3, ls=(0, (4, 2.5)), label="a ray at time 0"),
               Line2D([], [], color=INK, lw=1.9, label=r"the same ray carried by the vortex $u=r\,V(r)\,e_\theta$ for a time $\tau$")]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(left / W, 0.0), ncol=2, frameon=False,
               fontsize=9.5, handlelength=2.6, columnspacing=2.2)
    for ext in ("png", "svg"):
        fig.savefig(os.path.join(out, "log-polar-map." + ext))
    plt.close(fig)


# ------------------------------------------------------------------------------------------ solver

def solve(nu, k, T, N, dt, flow=True, frame_times=(), s_min=-3.2, s_max=2.8):
    """Times, norms ||f(t)||/||f(0)|| in L^2 of the plane, energy-balance residuals, g(t, s) at frame_times, s."""
    s = np.linspace(s_min, s_max, N + 1)[1:-1]            # interior points; g = 0 at the two ends
    ds = (s_max - s_min) / N
    w = np.exp(2 * s)                                     # the weight of dX dY = e^{2s} ds dtheta
    om = omega(np.exp(s)) if flow else 0 * s
    # w dg/dt = L g,  L = -i k om w + nu (D2 - k^2);  Crank-Nicolson: (w - dt/2 L) g_new = (w + dt/2 L) g_old
    diag = -1j * k * om * w + nu * (-2 / ds ** 2 - k ** 2)
    off = nu / ds ** 2
    ab = np.zeros((3, N - 1), dtype=complex)
    ab[0, 1:] = -dt / 2 * off
    ab[1, :] = w - dt / 2 * diag
    ab[2, :-1] = -dt / 2 * off
    g = np.exp(-(s / 0.8) ** 4).astype(complex)
    steps = int(round(T / dt))
    times = dt * np.arange(steps + 1)
    sq = np.empty(steps + 1)                              # int |g|^2 e^{2s} ds
    dissip = np.empty(steps + 1)                          # int |d_s g|^2 + k^2 |g|^2 ds
    frames, targets, j = [], list(frame_times), 0
    for n in range(steps + 1):
        sq[n] = (np.abs(g) ** 2 * w).sum() * ds
        dg = np.diff(np.concatenate([[0], g, [0]])) / ds
        dissip[n] = (np.abs(dg) ** 2).sum() * ds + k ** 2 * (np.abs(g) ** 2).sum() * ds
        while j < len(targets) and targets[j] <= times[n] + dt / 2:
            frames.append(g.copy())
            j += 1
        if n == steps:
            break
        rhs = (w + dt / 2 * diag) * g
        rhs[1:] += dt / 2 * off * g[:-1]
        rhs[:-1] += dt / 2 * off * g[1:]
        g = solve_banded((1, 1), ab, rhs)
    integral = np.concatenate([[0.0], np.cumsum((dissip[1:] + dissip[:-1]) / 2) * dt])
    residual = np.abs(sq + 2 * nu * integral - sq[0]) / sq[0]
    return times, np.sqrt(sq / sq[0]), residual, frames, s


# ------------------------------------------------------------------------------------------- video

class Panels:
    """The pixels of the two panels, and the interpolation from the grid in s."""

    def __init__(self, s, k, s_lo, s_hi, n=440):
        self.s, self.k, self.s_lo, self.s_hi = s, k, s_lo, s_hi
        R = np.exp(s_hi)
        x = np.linspace(-R, R, n)
        X, Y = np.meshgrid(x, x)
        r = np.hypot(X, Y)
        self.logr = np.log(np.maximum(r, 1e-12))
        self.inside = (self.logr <= s_hi) & (self.logr >= s[0])
        th = np.arctan2(Y, X)
        self.c, self.sn = np.cos(k * th), np.sin(k * th)
        self.R = R
        self.sv = np.linspace(s_lo, s_hi, int(round(n * 1.0)))
        tv = np.linspace(0, 2 * np.pi, int(round(n * 2 * np.pi / (s_hi - s_lo))))
        self.ct, self.st = np.cos(k * tv), np.sin(k * tv)

    def plane(self, g):
        gr = np.interp(self.logr, self.s, g.real)
        gi = np.interp(self.logr, self.s, g.imag)
        f = gr * self.c - gi * self.sn
        return np.where(self.inside, f, np.nan)      # nothing is drawn outside the disc shown

    def strip(self, g):
        gr = np.interp(self.sv, self.s, g.real)
        gi = np.interp(self.sv, self.s, g.imag)
        return gr[:, None] * self.ct[None, :] - gi[:, None] * self.st[None, :]


def draw_frame(path, t, g, P, nu, dpi=100):
    s_lo, s_hi, R = P.s_lo, P.s_hi, P.R
    side, gap, bottom, top = 2.95, 0.62, 0.62, 1.12
    wide = side * 2 * np.pi / (s_hi - s_lo)
    W = 11.2
    left = 0.45
    H = bottom + side + top
    H = round(H * dpi / 2) * 2 / dpi
    fig = plt.figure(figsize=(W, H), dpi=dpi)
    y0 = bottom
    ax = fig.add_axes([left / W, y0 / H, side / W, side / H])
    bx = fig.add_axes([(left + side + gap) / W, y0 / H, wide / W, side / H])
    tt = np.linspace(0, 2 * np.pi, 300)

    ax.imshow(P.plane(g), origin="lower", extent=[-R, R, -R, R], cmap="RdBu_r", vmin=-1, vmax=1, interpolation="bilinear")
    for s, ls in ((-1, (0, (3, 3))), (0, "-"), (1, (0, (3, 3)))):
        ax.plot(np.exp(s) * np.cos(tt), np.exp(s) * np.sin(tt), color=INK, lw=0.7, ls=ls, alpha=0.55)
    ax.plot(R * np.cos(tt), R * np.sin(tt), color=GRID, lw=0.8)
    ax.set_xlim(-R, R); ax.set_ylim(-R, R); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(r"In the plane:  a vortex,  $u=r\,V(r)\,e_\theta$", fontsize=14, pad=8)

    bx.imshow(P.strip(g), origin="lower", extent=[0, 2 * np.pi, s_lo, s_hi], cmap="RdBu_r", vmin=-1, vmax=1,
              interpolation="bilinear")
    for s, ls in ((-1, (0, (3, 3))), (0, "-"), (1, (0, (3, 3)))):
        bx.plot([0, 2 * np.pi], [s, s], color=INK, lw=0.7, ls=ls, alpha=0.55)
    bx.set_xlim(0, 2 * np.pi); bx.set_ylim(s_lo, s_hi); bx.set_aspect("equal")
    bx.set_xticks([0, np.pi, 2 * np.pi]); bx.set_xticklabels(["0", r"$\pi$", r"$2\pi$"], fontsize=11)
    bx.yaxis.tick_right(); bx.set_yticks([-1, 0, 1]); bx.set_yticklabels(["$-1$", "$0$", "$1$"], fontsize=11)
    bx.tick_params(length=3, width=0.8)
    for sp in bx.spines.values():
        sp.set_linewidth(0.8)
    bx.set_xlabel(r"$\theta$", fontsize=13, labelpad=0)
    bx.text(2 * np.pi + 0.52, 0.5 * (s_lo + s_hi), r"$s=\log r$", fontsize=13, rotation=90, va="center", ha="center")
    bx.set_title(r"In log-polar coordinates:  a shear flow,  $u=(V(e^s),\,0)$", fontsize=14, pad=8)

    fig.suptitle(r"$V(r)=1/(1+r^2)$,  diffusivity $\nu=%s$" % sci(nu) + "        t = %d" % round(t), fontsize=15,
                 y=1 - 0.3 / H)
    fig.savefig(path)
    plt.close(fig)


def sci(x):
    e = int(np.floor(np.log10(x)))
    m = x / 10.0 ** e
    return "10^{%d}" % e if abs(m - 1) < 1e-9 else r"%g\times10^{%d}" % (m, e)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=".", help="folder for the figure, the video and the checks")
    ap.add_argument("--nu", type=float, default=1e-3)
    ap.add_argument("--k", type=int, default=2, help="angular Fourier mode of the datum")
    ap.add_argument("--T", type=float, default=40.0)
    ap.add_argument("--N", type=int, default=1500, help="intervals in s")
    ap.add_argument("--dt", type=float, default=0.01)
    ap.add_argument("--duration", type=float, default=15.0, help="length of the video in seconds")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--hold", type=float, default=1.5, help="seconds the last frame is held")
    ap.add_argument("--only", default="", help="'map', 'check' or 'stills' to skip the rest")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    draw_map(a.out)
    if a.only == "map":
        return
    frame_times = a.T * np.linspace(0, 1, int(round(a.duration * a.fps)))
    times, norms, residual, frames, s = solve(a.nu, a.k, a.T, a.N, a.dt, True, frame_times)
    _, still, residual0, _, _ = solve(a.nu, a.k, a.T, a.N, a.dt, False)
    times2, norms2, residual2, _, _ = solve(a.nu, a.k, a.T, 2 * a.N, a.dt / 2, True)
    diff = np.abs(norms2[::2] - norms) / norms2[::2]
    lines = ["V(r) = 1/(1+r^2), datum cos(%d theta) exp(-(s/0.8)^4), nu = %g, T = %g" % (a.k, a.nu, a.T),
             "N = %d intervals in s on [-3.2, 2.8], dt = %g (Crank-Nicolson, centred differences)" % (a.N, a.dt),
             "norm ratio at t = T: with the vortex %.6e, without the flow %.6e" % (norms[-1], still[-1]),
             "largest relative difference of the norms with N = %d, dt = %g: %.2e" % (2 * a.N, a.dt / 2, diff.max()),
             "largest energy-balance residual (relative to the initial energy): N = %d: %.2e; N = %d: %.2e; no flow: %.2e"
             % (a.N, residual.max(), 2 * a.N, residual2.max(), residual0.max()),
             "largest |g| at the two ends of the grid over the frames: %.2e" % max(max(abs(g[0]), abs(g[-1])) for g in frames)]
    open(os.path.join(a.out, "log-polar-check.txt"), "w").write("\n".join(lines) + "\n")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4), dpi=100)
    ax1.semilogy(times, still, color=RUST, lw=2, label="without the flow")
    ax1.semilogy(times, norms, color=BLUE, lw=2, label="vortex, N=%d, dt=%g" % (a.N, a.dt))
    ax1.semilogy(times2, norms2, color="k", lw=1, ls="--", label="vortex, N=%d, dt=%g" % (2 * a.N, a.dt / 2))
    ax1.set_xlabel("time t"); ax1.set_ylabel("norm ratio"); ax1.legend(frameon=False, fontsize=9)
    ax2.semilogy(times[1:], diff[1:] + 1e-16, color=BLUE, lw=1.5, label="relative difference of the two runs")
    ax2.semilogy(times[1:], residual[1:] + 1e-16, color="#6b7280", lw=1.5, label="energy-balance residual")
    ax2.set_xlabel("time t"); ax2.legend(frameon=False, fontsize=9); ax2.set_title("Checks")
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "log-polar-check.png"))
    plt.close(fig)
    print("\n".join(lines))
    if a.only == "check":
        return
    P = Panels(s, a.k, -1.7, 1.2)
    if a.only == "stills":
        for q in (0.0, 0.1, 0.25, 0.5, 1.0):
            i = int(round(q * (len(frame_times) - 1)))
            draw_frame(os.path.join(a.out, "still-%03d.png" % round(100 * q)), frame_times[i], frames[i], P, a.nu)
        return
    with tempfile.TemporaryDirectory() as tmp:
        for i, (t, g) in enumerate(zip(frame_times, frames)):
            draw_frame(os.path.join(tmp, "f%04d.png" % i), t, g, P, a.nu)
        poster = min(range(len(frame_times)), key=lambda i: abs(frame_times[i] - 0.2 * a.T))
        shutil.copyfile(os.path.join(tmp, "f%04d.png" % poster), os.path.join(a.out, "log-polar-poster.png"))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps),
                        "-i", os.path.join(tmp, "f%04d.png"), "-vf", "tpad=stop_mode=clone:stop_duration=%g" % a.hold,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "slow", "-movflags", "+faststart",
                        os.path.join(a.out, "log-polar.mp4")], check=True)


if __name__ == "__main__":
    main()

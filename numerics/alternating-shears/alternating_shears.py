#!/usr/bin/env python3
"""Steady shear versus randomly shifted alternating shears (Pierrehumbert's model) on the torus [0, 2pi)^2.

    d_t f + u . grad f = nu (d_xx + d_yy) f,      f(0, x, y) = cos x,

with the alternating shears
    u = (sin(y + phi_n), 0)   for 2nh <= t < (2n+1)h,
    u = (0, sin(x + psi_n))   for (2n+1)h <= t < (2n+2)h,
the phases phi_n, psi_n independent and uniform on [0, 2pi) (random generator seeded with --seed), each shear
acting for a time h = --h; compared with the steady shear u = (sin y, 0) (the flow of heat_vs_shear.py) and with
the heat equation. Both velocity fields satisfy |u| <= 1.

Method. Alternating shears: Fourier pseudo-spectral method on an N x N grid with Strang splitting, time step dt;
a transport step is exact (each row, or each column, is shifted by dt sin(.) through its Fourier coefficients) and
a diffusion step is exact in Fourier variables. Steady shear: one Fourier mode in x, as in heat_vs_shear.py.
The norm reported is ||f(t)|| / ||f(0)|| in L^2.

Checks (written to alternating-shears-check.txt and alternating-shears-check.png):
  * the video run is repeated with 2N modes per direction and time step dt/2, and the norms are compared;
  * energy balance: ||f(t)||^2 + 2 nu int_0^t ||grad f||^2 ds = ||f(0)||^2;
  * dissipation time T_half (first time with ||f(t)|| <= ||f(0)||/2) for nu = 1e-2, 1e-3, 1e-4, 1e-5, same phases,
    for the alternating shears (with N and 2N modes), the steady shear and the heat equation (ln 2 / nu).

Outputs, in --out: alternating-shears.mp4 (video, time running uniformly, last frame held --hold seconds),
alternating-shears-poster.png, alternating-shears-check.png and alternating-shears-check.txt.
Needs NumPy, SciPy, Matplotlib and ffmpeg (libx264). Run:  python3 alternating_shears.py --out ../../wiki/media
(about 15 minutes, most of it for the checks; --no-scan skips the dissipation-time scan).

Drafted by Claude (AI) on 8 November 2026 for the wiki "Enhanced dissipation for passive scalars";
record: page Numerical methods, section num-alternating-shears.
"""
import argparse
import os
import shutil
import subprocess
import tempfile

import numpy as np
import scipy.fft as sfft
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HEAT_COLOR = "#b4532a"
SHEAR_COLOR = "#1f4e79"
ALT_COLOR = "#1d6a66"
WORKERS = os.cpu_count() or 1


def solve_alternating(nu, N, h, T, dt, seed, frame_times=(), nx=256, stop_at_half=False):
    """Times, norms, energy-balance residuals, fields at frame_times (nx-by-nx, rows: y), T_half."""
    k = sfft.fftfreq(N, 1.0 / N)                       # integer wavenumbers
    KY, KX = np.meshgrid(k, k, indexing="ij")          # axis 0: y, axis 1: x
    K2 = KX ** 2 + KY ** 2
    half = np.exp(-nu * K2 * dt / 2)
    z = 2 * np.pi * np.arange(N) / N
    X = np.broadcast_to(z[None, :], (N, N))
    F = sfft.fft2(np.cos(X), workers=WORKERS)
    n0 = np.sum(np.abs(F) ** 2)
    rng = np.random.default_rng(seed)
    steps = int(round(T / dt))
    per = int(round(h / dt))
    if abs(per * dt - h) > 1e-12:
        raise SystemExit("h must be a multiple of dt")
    times = dt * np.arange(steps + 1)
    sq = np.full(steps + 1, np.nan)
    dissip = np.full(steps + 1, np.nan)
    frames, targets, j, t_half = [], list(frame_times), 0, None
    stride = max(1, N // nx)
    for n in range(steps + 1):
        power = np.abs(F) ** 2 / n0
        sq[n] = power.sum()
        dissip[n] = (K2 * power).sum()
        if t_half is None and sq[n] <= 0.25:
            t_half = times[n]
            if stop_at_half:
                break
        while j < len(targets) and targets[j] <= times[n] + dt / 2:
            frames.append(np.real(sfft.ifft2(F, workers=WORKERS))[::stride, ::stride].copy())
            j += 1
        if n == steps:
            break
        if n % per == 0:                               # a new shear, with a new random phase
            phase = rng.uniform(0, 2 * np.pi)
            if (n // per) % 2 == 0:                    # u = (sin(y + phase), 0): row y shifted in x
                P = np.exp(-1j * np.outer(dt * np.sin(z + phase), k))      # [y, k_x]
                axis = 0
            else:                                      # u = (0, sin(x + phase)): column x shifted in y
                P = np.exp(-1j * np.outer(k, dt * np.sin(z + phase)))      # [k_y, x]
                axis = 1
        F *= half
        G = sfft.ifft(F, axis=axis, workers=WORKERS)
        G *= P
        F = sfft.fft(G, axis=axis, workers=WORKERS)
        F *= half
    m = np.isfinite(sq)
    times, sq, dissip = times[m], sq[m], dissip[m]
    integral = np.concatenate([[0.0], np.cumsum((dissip[1:] + dissip[:-1]) / 2) * dt])
    residual = np.abs(sq + 2 * nu * integral - 1.0)
    return times, np.sqrt(sq), residual, frames, t_half


def solve_shear(nu, T, N, dt, frame_times=()):
    """Steady shear u = (sin y, 0), datum cos x: f = Re(g(t, y) e^{ix}) (as in heat_vs_shear.py)."""
    y = 2 * np.pi * np.arange(N) / N
    eta = np.fft.fftfreq(N, d=1.0 / N)
    symbol = eta ** 2 + 1.0
    half = np.exp(-nu * symbol * dt / 2)
    transport = np.exp(-1j * np.sin(y) * dt)
    ghat = np.fft.fft(np.ones(N, dtype=complex))
    steps = int(round(T / dt))
    times = dt * np.arange(steps + 1)
    sq = np.empty(steps + 1)
    frames, targets, j = [], list(frame_times), 0
    for n in range(steps + 1):
        sq[n] = (np.abs(ghat) ** 2).sum() / N ** 2
        while j < len(targets) and targets[j] <= times[n] + dt / 2:
            frames.append(np.fft.ifft(ghat))
            j += 1
        if n == steps:
            break
        ghat *= half
        ghat = np.fft.fft(np.fft.ifft(ghat) * transport) * half
    norms = np.sqrt(sq)
    below = np.nonzero(norms <= 0.5)[0]
    return times, norms, frames, (times[below[0]] if len(below) else None)


def fmt(t):
    return "%.3f" % t if t is not None else "> T"


def shear_field(g, nx):
    step = max(1, len(g) // nx)
    x = 2 * np.pi * np.arange(nx) / nx
    return np.real(g[::step][:, None] * np.exp(1j * x)[None, :])


def draw_frame(path, t, f_alt, g_shear, nu, h, curves, ymin, T):
    nx = f_alt.shape[0]
    fig = plt.figure(figsize=(11.2, 7.2), dpi=100)
    gs = fig.add_gridspec(2, 2, height_ratios=[3.6, 1.15], hspace=0.3, wspace=0.06,
                          left=0.08, right=0.97, top=0.845, bottom=0.095)
    for col, (data, title) in enumerate([(shear_field(g_shear, nx), r"Shear flow:  $u = (\sin y,\, 0)$"),
                                         (f_alt, "Alternating shears, random phases")]):
        ax = fig.add_subplot(gs[0, col])
        ax.imshow(data, origin="lower", extent=[0, 2 * np.pi, 0, 2 * np.pi], cmap="RdBu_r",
                  vmin=-1, vmax=1, interpolation="bilinear")
        ax.set_title(title, fontsize=17, pad=8)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_aspect("equal")
    fig.suptitle(r"Same initial datum $f_0 = \cos x$, same diffusivity $\nu = 10^{%d}$, $|u| \leq 1$"
                 % round(np.log10(nu)) + "        t = %d" % round(t), fontsize=17, y=0.975)
    ax = fig.add_subplot(gs[1, :])
    for times, norms, color, label in curves:
        k = np.searchsorted(times, t, side="right")
        ax.semilogy(times, norms, color=color, alpha=0.18, lw=2)
        ax.semilogy(times[:k], norms[:k], color=color, lw=2.4, label=label)
    ax.axvline(t, color="#888888", lw=1)
    ax.set_xlim(0, T); ax.set_ylim(ymin, 1.5)
    ax.set_yticks([10.0 ** e for e in range(int(np.log10(ymin)), 1)])
    ax.set_xlabel("time  t", fontsize=13)
    ax.set_ylabel(r"$\|f(t)\|\,/\,\|f_0\|$", fontsize=14)
    ax.tick_params(labelsize=11)
    ax.legend(loc="lower left", fontsize=12, frameon=False, ncol=3)
    fig.savefig(path)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=".", help="folder for the video and the figures")
    ap.add_argument("--nu", type=float, default=1e-4)
    ap.add_argument("--h", type=float, default=3.0, help="time during which each shear acts")
    ap.add_argument("--T", type=float, default=60.0)
    ap.add_argument("--N", type=int, default=512, help="Fourier modes per direction")
    ap.add_argument("--dt", type=float, default=0.0125)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--duration", type=float, default=20.0, help="length of the video in seconds")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--hold", type=float, default=1.5, help="seconds the last frame is held")
    ap.add_argument("--no-scan", action="store_true", help="skip the dissipation-time scan")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    frame_times = np.linspace(0, a.T, int(round(a.duration * a.fps)))
    # the video run, the steady shear and the heat equation
    times, norms, residual, frames, t_half = solve_alternating(a.nu, a.N, a.h, a.T, a.dt, a.seed, frame_times)
    s_times, s_norms, s_frames, s_half = solve_shear(a.nu, a.T, 2 * a.N, a.dt, frame_times)
    heat = np.exp(-a.nu * times)
    # check: the same run with 2N and dt/2
    times2, norms2, residual2, _, t_half2 = solve_alternating(a.nu, 2 * a.N, a.h, a.T, a.dt / 2, a.seed)
    diff = np.abs(norms2[::2] - norms) / norms2[::2]
    lines = ["nu=%g h=%g T=%g N=%d dt=%g seed=%d frames=%d fps=%d" % (a.nu, a.h, a.T, a.N, a.dt, a.seed,
                                                                      len(frame_times), a.fps),
             "final norm: alternating %.4e, steady shear %.4e, heat %.4e" % (norms[-1], s_norms[-1], heat[-1]),
             "T_half: alternating %s (2N, dt/2: %s), steady shear %s, heat %.1f" % (
                 fmt(t_half), fmt(t_half2), fmt(s_half), np.log(2) / a.nu),
             "max relative difference of the norms with (2N, dt/2): %.2e" % diff.max(),
             "max energy-balance residual: %.2e (2N, dt/2: %.2e)" % (residual.max(), residual2.max())]
    scan = []
    if not a.no_scan:
        lines.append("dissipation time T_half (same phases, h=%g):" % a.h)
        lines.append("  nu        N     alternating  alternating(2N)  steady shear  heat")
        for nu, N in ((1e-2, 128), (1e-3, 256), (1e-4, 512), (1e-5, 1024)):
            _, _, _, _, ta = solve_alternating(nu, N, a.h, 200, a.dt, a.seed, stop_at_half=True)
            _, _, _, _, ta2 = solve_alternating(nu, 2 * N, a.h, 200, a.dt, a.seed, stop_at_half=True)
            _, _, _, ts = solve_shear(nu, 2000, 2048, 0.02)
            scan.append((nu, ta, ta2, ts, np.log(2) / nu))
            lines.append("  %-8g  %-5d %-12.3f %-16.3f %-13.2f %.1f" % (nu, N, ta, ta2, ts, np.log(2) / nu))
            print(lines[-1], flush=True)
    with open(os.path.join(a.out, "alternating-shears-check.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    # check figure
    ymin = 10 ** np.floor(np.log10(min(norms.min(), s_norms.min())))
    fig, axes = plt.subplots(1, 2 if scan else 1, figsize=(11, 4.2), dpi=100, squeeze=False)
    ax1 = axes[0, 0]
    ax1.semilogy(times, heat, color=HEAT_COLOR, lw=2, label="heat equation (exact)")
    ax1.semilogy(s_times, s_norms, color=SHEAR_COLOR, lw=2, label="steady shear")
    ax1.semilogy(times, norms, color=ALT_COLOR, lw=2, label="alternating shears, N=%d, dt=%g" % (a.N, a.dt))
    ax1.semilogy(times2, norms2, color="k", lw=1, ls="--", label="alternating shears, N=%d, dt=%g" % (2 * a.N, a.dt / 2))
    ax1.set_xlabel("time t"); ax1.set_ylabel("norm ratio"); ax1.legend(frameon=False, fontsize=9)
    ax1.set_title(r"Norms, $\nu = %g$ (log scale)" % a.nu)
    if scan:
        ax2 = axes[0, 1]
        nus = np.array([s[0] for s in scan])
        ax2.loglog(1 / nus, [s[4] for s in scan], "o-", color=HEAT_COLOR, label=r"heat: $\ln 2/\nu$")
        ax2.loglog(1 / nus, [s[3] for s in scan], "o-", color=SHEAR_COLOR, label="steady shear")
        ax2.loglog(1 / nus, [s[1] for s in scan], "o-", color=ALT_COLOR, label="alternating shears")
        ax2.loglog(1 / nus, [s[2] for s in scan], "x", color="k", label="alternating shears, 2N")
        ax2.set_xlabel(r"$1/\nu$"); ax2.set_ylabel(r"$T_{1/2}$"); ax2.legend(frameon=False, fontsize=9)
        ax2.set_title(r"Time for the norm to halve")
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "alternating-shears-check.png"))
    plt.close(fig)
    # video
    curves = [(times, heat, HEAT_COLOR, "heat equation"), (s_times, s_norms, SHEAR_COLOR, "shear flow"),
              (times, norms, ALT_COLOR, "alternating shears")]
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(frame_times):
            draw_frame(os.path.join(tmp, "f%04d.png" % i), t, frames[i], s_frames[i], a.nu, a.h, curves, ymin, a.T)
        poster = min(range(len(frame_times)), key=lambda i: abs(frame_times[i] - 0.2 * a.T))
        shutil.copyfile(os.path.join(tmp, "f%04d.png" % poster), os.path.join(a.out, "alternating-shears-poster.png"))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps),
                        "-i", os.path.join(tmp, "f%04d.png"), "-vf", "tpad=stop_mode=clone:stop_duration=%g" % a.hold,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "26", "-preset", "slow", "-movflags", "+faststart",
                        os.path.join(a.out, "alternating-shears.mp4")], check=True)
    print("\n".join(lines))


if __name__ == "__main__":
    main()

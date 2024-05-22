import numpy as np
import ctypes
from math import tau
from numba import vectorize, njit
from numba.types import float64, UniTuple, string
from numba.extending import get_cython_function_address


addr = get_cython_function_address("scipy.special.cython_special", "__pyx_fuse_1erf")
functype = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_double)
erf_fn = functype(addr)


@vectorize([float64(float64)])
def vec_erf(x):
    return erf_fn(x)


@njit(float64[:, :](float64[:, :]))
def erf_njit(x):
    return vec_erf(x)


# Probability density function for a normal distribution
@njit(float64[:, :](float64[:, :], float64, float64))
def norm_pdf(x, mu, sigma):
    variance = sigma**2.0
    return np.exp((x - mu) ** 2.0 / (-2.0 * variance)) / np.sqrt(tau * variance)


# Cumulative distribution function for a normal distribution
@njit(float64[:, :](float64[:, :], float64, float64))
def norm_cdf(x, mu, sigma):
    return 0.5 * (1.0 + erf_njit((x - mu) / (sigma * np.sqrt(2.0))))


# S is spot price, K is strike price, vol is implied volatility
# T is time to expiration, r is risk-free rate, q is dividend yield
@njit(
    UniTuple(float64[:, :], 3)(
        float64[:, :], float64[:], float64[:], float64[:], float64, float64
    )
)
def calc_dp_cdf_pdf(S, K, vol, T, r, q):
    dp = (np.log(S / K) + (r - q + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    cdf_dp = norm_cdf(dp, 0.0, 1.0)
    pdf_dp = norm_pdf(dp, 0.0, 1.0)
    return dp, cdf_dp, pdf_dp


# Black-Scholes Pricing Formula


@njit(
    float64[:, :](float64[:, :], float64[:], float64, string, float64[:], float64[:, :])
)
def calc_delta_ex(S, T, q, opt_type, OI, cdf_dp):
    if opt_type == "call":
        delta = np.exp(-q * T) * cdf_dp
    else:
        delta = -np.exp(-q * T) * (1 - cdf_dp)
    # change in option price per one percent move in underlying
    return delta * OI * S


@njit(
    float64[:, :](
        float64[:, :], float64[:], float64[:], float64, float64[:], float64[:, :]
    )
)
def calc_gamma_ex(S, vol, T, q, OI, pdf_dp):
    gamma = np.exp(-q * T) * pdf_dp / (S * vol * np.sqrt(T))
    # change in delta per one percent move in underlying
    return gamma * OI * S * S  # Gamma is same formula for calls and puts


@njit(
    float64[:, :](
        float64[:, :],
        float64[:],
        float64[:],
        float64,
        float64[:],
        float64[:, :],
        float64[:, :],
    )
)
def calc_vanna_ex(S, vol, T, q, OI, dp, pdf_dp):
    dm = dp - vol * np.sqrt(T)
    vanna = -np.exp(-q * T) * pdf_dp * (dm / vol)
    # change in delta per one percent move in IV
    # or change in vega per one percent move in underlying
    return vanna * OI * S * vol  # Vanna is same formula for calls and puts


@njit(
    float64[:, :](
        float64[:, :],
        float64[:],
        float64[:],
        float64,
        float64,
        string,
        float64[:],
        float64[:, :],
        float64[:, :],
        float64[:, :],
    )
)
def calc_charm_ex(S, vol, T, r, q, opt_type, OI, dp, cdf_dp, pdf_dp):
    dm = dp - vol * np.sqrt(T)
    if opt_type == "call":
        charm = (q * np.exp(-q * T) * cdf_dp) - np.exp(-q * T) * pdf_dp * (
            2 * (r - q) * T - dm * vol * np.sqrt(T)
        ) / (2 * T * vol * np.sqrt(T))
    else:
        charm = (-q * np.exp(-q * T) * (1 - cdf_dp)) - np.exp(-q * T) * pdf_dp * (
            2 * (r - q) * T - dm * vol * np.sqrt(T)
        ) / (2 * T * vol * np.sqrt(T))
    # change in delta per day until expiration
    return charm * OI * S * T

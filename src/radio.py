import numpy as np
from scipy.special import erfc

def quantize (x, bits):
    """Uniform quantizer: real values -> integers from 0 to 2**bits-1"""
    x_min = x.min()
    x_max = x.max()
    levels = 2**bits -1
    q = np.round((x-x_min)/(x_max-x_min)*levels)
    return q.astype(int), x_min, x_max

def dequantize(q, bits, x_min, x_max):
    """Integers-> approximate real values (the receiver needs x_min and x_max)"""
    levels = 2**bits-1
    return q / levels * (x_max-x_min) + x_min

def to_bits(values, n_bits):
    """Integers-> stream of bits, n_bits per integer (msb first)"""
    columns = []
    for i in range(n_bits-1, -1, -1):
        columns.append((values >>i) &1)
    return np.stack(columns, axis = 1).flatten()
    
def from_bits(bit_stream, n_bits):
     """Stream of bits -> integers, n_bits per integer (inverse of to_bits)."""
     groups = bit_stream.reshape(-1, n_bits)
     weights = 2 ** np.arange(n_bits-1, -1, -1)
     return (groups * weights).sum(axis=1)
 

def gray_pam_table(k):
    """Amplitude of each k-bit label for a Gray-mapped M-PAM (M = 2**k)""" 
    M = 2** k
    amplitudes = np.zeros(M)
    for i in range(M):
        label = i ^ (i>>1)
        amplitudes[label] = 2*i -(M-1)
    return amplitudes

def map_pam(bit_stream, k):
   """Bits -> M-PAM symbols. Pads with zeros if the bits are not a multiple of k."""
   padding = (-len(bit_stream)) % k
   padded = np.concatenate([bit_stream, np.zeros(padding, dtype = int)])
   labels = from_bits(padded, k)
   return gray_pam_table(k)[labels], padding

def demap_pam(received, k, n_padding):
    """Decision (nearest amplitude) + demapping: received values -> bits."""
    M = 2**k
    index = np.round((received + (M - 1)) / 2)
    index = np.clip(index, 0, M-1).astype(int)
    labels = index ^ (index >>1)
    bits = to_bits(labels, k)
    if n_padding > 0: 
        bits = bits[:-n_padding]
    return bits

def add_noise(symbols, k, ebn0_db, seed=42):
    """Add white Gaussian noise to M-PAM symbols for a given Eb/N0 in dB"""
    M = 2**k
    Es = (M**2 -1)/3
    ebn0 = 10** (ebn0_db/10)
    N0 = Es/ (k*ebn0)
    sigma = np.sqrt(N0/2)
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, sigma, len(symbols))
    return symbols + noise

def decide_pam(received, k):
    """Decides the nearest amplitude in a M-PAM map for each received value"""
    M = 2**k
    index = np.round((received + (M - 1)) / 2)
    index = np.clip(index, 0, M-1)
    return 2 * index -(M-1)

def theoretical_ser (k, ebn0_db):
    """Theorycal symbol error rate of M-PAM on an AWGN Channel"""
    M = 2**k
    ebn0 = 10**(ebn0_db/10)
    x = np.sqrt(6*k*ebn0 /(M**2 -1))
    q_function = 0.5 * erfc(x/np.sqrt(2))
    return 2 * (1-1/M)* q_function

    
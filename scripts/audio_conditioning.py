"""Input conditioning for the wake keyword spotter. numpy only, streaming, 20 ms frames.

Used by `wake_worker.py --live` (preference `input_conditioning`: `auto` applies the chain, `off` does not).
It runs only in front of the keyword spotter: the Core still receives the raw frames, so capture, STT and
VAD are unchanged. Input and output are float32 in [-1, 1] at 16 kHz, 320 samples per call.

Stages, in the order they run (each one is switched on by its Config flag):
- high-pass: 257-tap FIR at 100 Hz (removes DC and rumble). Group delay 128 samples (8 ms).
- pre-emphasis: first-order, 0.97.
- spectral noise suppression: sqrt-Hann STFT (320 window, hop 160). The per-bin noise mean is updated
  from quiet frames (frame power near its running minimum); spectral subtraction with a gain floor of
  -20 dB. Delay 160 samples (10 ms).
- AGC: block RMS follower with attack/release, gain toward a target level, between -12 and +24 dB.
- gate: soft expander below a floor that follows quiet blocks (up to 12 dB of attenuation).
Only `AUTO_CHAIN` (high-pass alone) is applied in production. The other chains exist for the evaluation
in docs/A9-wake-real-noise.md (harness: /tmp/gideon-wake-lab/realnoise, which runs this same module).
"""
from dataclasses import dataclass
import numpy as np

RATE = 16000
FRAME = 320
HOP = 160
HPF_TAPS = 257
PREEMPH_COEF = 0.97


@dataclass(frozen=True)
class Config:
    hpf: bool = False
    hpf_hz: float = 100.0
    ns: bool = False
    ns_alpha: float = 0.003      # per-hop rise of the frame-power floor (about 2.6 dB/s)
    ns_mix: float = 0.05         # per-hop weight of a quiet frame in the per-bin noise mean
    ns_beta: float = 1.0         # subtraction factor
    ns_gain_floor: float = 0.1   # -20 dB
    agc: bool = False
    agc_target_db: float = -23.0
    agc_max_gain_db: float = 24.0
    agc_min_gain_db: float = -12.0
    agc_attack: float = 0.5      # per 20 ms block
    agc_release: float = 0.05
    gate: bool = False
    gate_margin_db: float = 6.0
    gate_range_db: float = 12.0
    gate_rise: float = 0.02      # per block, floor follows quiet blocks slowly
    preemph: bool = False


OFF = Config()
# The chain of preference `input_conditioning` = auto: the winner of docs/A9-wake-real-noise.md (DC + 100 Hz HPF).
AUTO_CHAIN = Config(hpf=True)


def named(name):
    """Named chains of the A9 evaluation; 'hpf' is AUTO_CHAIN, the one the worker applies for `auto`."""
    table = {
        'off': OFF,
        'hpf': AUTO_CHAIN,
        'hpf_agc': Config(hpf=True, agc=True),
        'hpf_agc_gate': Config(hpf=True, agc=True, gate=True),
        'hpf_gate': Config(hpf=True, gate=True),
        'hpf_ns': Config(hpf=True, ns=True),
        'hpf_ns_agc_gate': Config(hpf=True, ns=True, agc=True, gate=True),
        'hpf_agc_gate_preemph': Config(hpf=True, agc=True, gate=True, preemph=True),
    }
    return table[name]


def hpf_taps(hz):
    centre = (HPF_TAPS - 1) // 2
    n = np.arange(HPF_TAPS) - centre
    fc = hz / RATE
    low = 2 * fc * np.sinc(2 * fc * n) * np.hamming(HPF_TAPS)
    low /= low.sum()
    high = -low
    high[centre] += 1.0
    return high.astype(np.float32)


class Conditioner:
    def __init__(self, config=OFF):
        self.config = config
        self.taps = hpf_taps(config.hpf_hz) if config.hpf else None
        self.hpf_state = np.zeros(HPF_TAPS - 1, dtype=np.float32)
        self.prev = 0.0
        self.window = np.sqrt(0.5 - 0.5 * np.cos(2 * np.pi * np.arange(FRAME) / FRAME)).astype(np.float32)
        self.frame_state = np.zeros(FRAME, dtype=np.float32)
        self.pending = np.zeros(HOP, dtype=np.float32)
        self.noise = None
        self.frame_floor = None
        self.agc_level = None
        self.agc_gain = 0.0
        self.gate_floor = None
        self.gate_gain = 0.0

    def process(self, block):
        x = np.asarray(block, dtype=np.float32)
        if x.shape != (FRAME,):
            raise ValueError('conditioning expects 320-sample frames')
        c = self.config
        if c.hpf:
            buf = np.concatenate([self.hpf_state, x])
            x = np.convolve(buf, self.taps, mode='valid').astype(np.float32)
            self.hpf_state = buf[-(HPF_TAPS - 1):]
        if c.preemph:
            y = x.copy()
            y[0] = x[0] - PREEMPH_COEF * self.prev
            y[1:] = x[1:] - PREEMPH_COEF * x[:-1]
            self.prev = float(x[-1])
            x = y
        if c.ns:
            x = self._suppress(x)
        if c.agc:
            x = self._agc(x)
        if c.gate:
            x = self._gate(x)
        return np.clip(x, -1.0, 1.0).astype(np.float32)

    def _suppress(self, x):
        c = self.config
        out = np.empty(FRAME, dtype=np.float32)
        for half in (0, HOP):
            hop = x[half:half + HOP]
            self.frame_state = np.concatenate([self.frame_state[HOP:], hop])
            spec = np.fft.rfft(self.frame_state * self.window, FRAME)
            power = (spec.real ** 2 + spec.imag ** 2).astype(np.float64)
            total = float(power.sum())
            if total > 1e-9:
                # Quiet frames (near the running minimum of the frame power) update the per-bin noise mean.
                if self.frame_floor is None or total < self.frame_floor:
                    self.frame_floor = total
                else:
                    self.frame_floor += c.ns_alpha * (total - self.frame_floor)
                if self.noise is None or total <= 2.0 * self.frame_floor:
                    self.noise = power.copy() if self.noise is None else (1 - c.ns_mix) * self.noise + c.ns_mix * power
            if self.noise is None:
                gain = np.ones_like(power)
            else:
                gain = np.sqrt(np.maximum(1 - c.ns_beta * self.noise / np.maximum(power, 1e-12), c.ns_gain_floor))
            frame = np.fft.irfft(spec * gain, FRAME).astype(np.float32) * self.window
            out[half:half + HOP] = self.pending + frame[:HOP]
            self.pending = frame[HOP:]
        # Output lags the input by one hop (10 ms): block k returns samples of block k-1 plus this block's first half.
        return out

    def _agc(self, x):
        c = self.config
        level = 10 * np.log10(float(np.mean(x.astype(np.float64) ** 2)) + 1e-10)
        if self.agc_level is None:
            self.agc_level = level
        coef = c.agc_attack if level > self.agc_level else c.agc_release
        self.agc_level += coef * (level - self.agc_level)
        gain_db = float(np.clip(c.agc_target_db - self.agc_level, c.agc_min_gain_db, c.agc_max_gain_db))
        gain = 10 ** (gain_db / 20)
        ramp = np.linspace(10 ** (self.agc_gain / 20), gain, FRAME, dtype=np.float32)
        self.agc_gain = gain_db
        return x * ramp

    def _gate(self, x):
        c = self.config
        level = 10 * np.log10(float(np.mean(x.astype(np.float64) ** 2)) + 1e-10)
        if self.gate_floor is None:
            self.gate_floor = level
        if level < self.gate_floor:
            self.gate_floor = level
        else:
            self.gate_floor += c.gate_rise * (level - self.gate_floor)
        shortfall = self.gate_floor + c.gate_margin_db - level
        atten_db = float(np.clip(shortfall, 0.0, c.gate_range_db))
        ramp = np.linspace(10 ** (-self.gate_gain / 20), 10 ** (-atten_db / 20), FRAME, dtype=np.float32)
        self.gate_gain = atten_db
        return x * ramp

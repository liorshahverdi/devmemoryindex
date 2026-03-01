import hashlib
import tempfile
import sounddevice as sd
import scipy.io.wavfile as wav
import whisper
from datetime import datetime
from core.schema import Memory
from core.embeddings import embed
from connectors.base import Connector


class VoiceConnector(Connector):
    name = "voice"

    def __init__(
        self,
        duration: int = 10,
        model_size: str = "base",  # "base" | "small" | "medium"
        repo: str | None = None,
    ):
        super().__init__()
        self.duration = duration
        self.model_size = model_size
        self.repo = repo
        self._model = None  # lazy-loaded

    def _get_model(self):
        if self._model is None:
            self._model = whisper.load_model(self.model_size)
        return self._model

    def collect(self) -> int:
        """Record audio, transcribe, and store as a memory. Returns 1 on success."""
        sample_rate = 16000
        audio = sd.rec(
            self.duration * sample_rate,
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        sd.wait()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav.write(f.name, sample_rate, audio)
            wav_path = f.name

        # Prepare in-memory waveform for Whisper to avoid calling external ffmpeg
        try:
            import numpy as np

            audio_for_whisper = audio.squeeze()
            if np.issubdtype(audio_for_whisper.dtype, np.integer):
                info = np.iinfo(audio_for_whisper.dtype)
                audio_for_whisper = audio_for_whisper.astype("float32") / float(info.max)
            else:
                audio_for_whisper = audio_for_whisper.astype("float32")

            result = self._get_model().transcribe(audio_for_whisper)
        except Exception:
            # Fallback to file-based transcription if in-memory path fails
            result = self._get_model().transcribe(wav_path)

        text = result["text"].strip()
        if not text:
            return 0

        # Guard A — Noise gate: reject mostly-silent recordings
        segments = result.get("segments", [])
        if segments:
            avg_no_speech = sum(s.get("no_speech_prob", 0.0) for s in segments) / len(segments)
            if avg_no_speech > 0.6:
                return 0  # Mostly silence or background noise — discard

        # Guard A — Minimum word count gate (Whisper can hallucinate short phrases from noise)
        if len(text.split()) < 4:
            return 0

        # Guard B — Speaker identity check (enrolled profile gate)
        from core.speaker_profile import load_profile, is_self

        profile = load_profile()
        if profile is not None:
            seg_emb = self._extract_speaker_embedding(wav_path)
            if seg_emb is not None and not is_self(seg_emb, profile, threshold=0.3):
                mem_type = "voice_ambient"
                importance = 0.3
                tags = ["voice", "ambient"]
            else:
                mem_type = "voice_note"
                importance = 0.8
                tags = ["voice"]
        else:
            # No profile enrolled — store as voice_note but flag it
            mem_type = "voice_note"
            importance = 0.8
            tags = ["voice"]

        mem_id = hashlib.sha256((text + "voice").encode()).hexdigest()

        if self.store.exists(mem_id):
            return 0

        memory = Memory(
            id=mem_id,
            type=mem_type,
            summary=text[:200],
            raw_text=text,
            source="voice",
            repo=self.repo,
            timestamp=datetime.utcnow(),
            tags=tags,
            importance=importance,
        )

        self.store.add(memory, embed(memory.summary))
        return 1

    def _extract_speaker_embedding(self, wav_path: str):
        """Extract speaker embedding using pyannote/embedding. Returns None on failure."""
        try:
            from pyannote.audio import Model, Inference
            model = Model.from_pretrained("pyannote/embedding", use_auth_token=True)

            # Try to load WAV into memory and pass waveform dict to avoid torchcodec/AudioDecoder
            try:
                import torch
                import numpy as np
                from scipy.io import wavfile as wavreader

                sample_rate, data = wavreader.read(wav_path)

                if np.issubdtype(data.dtype, np.integer):
                    info = np.iinfo(data.dtype)
                    data = data.astype("float32") / float(info.max)
                else:
                    data = data.astype("float32")

                if data.ndim == 1:
                    waveform = torch.from_numpy(data).unsqueeze(0)
                else:
                    waveform = torch.from_numpy(data.T)

                return Inference(model, window="whole")({"waveform": waveform, "sample_rate": int(sample_rate)})
            except Exception:
                # Fallback to file-path-based inference (may trigger AudioDecoder)
                return Inference(model, window="whole")(wav_path)
        except Exception:
            return None

"""Seed a fresh database.

* Creates the initial superuser (ADMIN_EMAIL / ADMIN_PASSWORD env vars, or defaults in dev).
* Syncs the AI provider catalogue into `ai_providers`.
* Generates a small library of procedurally synthesised, royalty-free music beds so
  projects have background music without any external download.

Idempotent - safe to run on every deploy:  `python -m scripts.seed`
"""

from __future__ import annotations

import io
import math
import os
import struct
import sys
import wave
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
for p in (BACKEND_ROOT, BACKEND_ROOT.parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import sync_session  # noqa: E402
from app.models.billing import Subscription  # noqa: E402
from app.models.enums import (  # noqa: E402
    AudioKind,
    CreditTransactionKind,
    MediaSource,
    PlanTier,
    ProviderKind,
)
from app.models.media import AudioAsset  # noqa: E402
from app.models.provider import AIProvider  # noqa: E402
from app.models.user import User  # noqa: E402
from app.providers import get_registry  # noqa: E402
from app.services.billing_service import add_credits_sync, apply_plan, ensure_subscription_sync  # noqa: E402
from app.services.media_service import save_audio_asset_sync  # noqa: E402

configure_logging()
log = get_logger("seed")

SAMPLE_RATE = 22050

# (name, mood, bpm, chord progression as semitone offsets from root, root Hz, brightness)
MUSIC_BEDS = [
    ("Calm Horizon", "calm", 72, [[0, 4, 7], [-3, 0, 4], [-5, -1, 2], [-7, -3, 0]], 220.0, 0.35),
    ("Documentary Pulse", "documentary", 96, [[0, 3, 7], [-2, 2, 5], [-4, 0, 3], [-5, -2, 2]], 196.0, 0.5),
    ("Uplifting Journey", "uplifting", 112, [[0, 4, 7], [5, 9, 12], [7, 11, 14], [5, 9, 12]], 261.6, 0.7),
    ("Deep Focus", "focus", 84, [[0, 7, 12], [-2, 5, 10], [-4, 3, 8], [-2, 5, 10]], 174.6, 0.3),
    ("Dramatic Tension", "dramatic", 66, [[0, 3, 7], [-1, 3, 6], [-4, 0, 3], [-6, -2, 1]], 146.8, 0.55),
    ("Tech Minimal", "tech", 120, [[0, 7, 12], [0, 7, 12], [-5, 2, 7], [-3, 4, 9]], 233.1, 0.6),
]


def _synth_music(bpm: int, progression: list[list[int]], root: float, brightness: float, seconds: int = 90) -> bytes:
    """Cheap additive synth: pad chords + soft arpeggio + kick, rendered to 16-bit mono WAV."""
    n = SAMPLE_RATE * seconds
    beat = 60.0 / bpm
    bar = beat * 4
    out = [0.0] * n
    two_pi = 2 * math.pi
    for i in range(n):
        t = i / SAMPLE_RATE
        chord = progression[int(t // bar) % len(progression)]
        # pad: 3 detuned voices per chord tone with slow tremolo
        pad = 0.0
        for semi in chord:
            f = root * (2 ** (semi / 12))
            pad += math.sin(two_pi * f * t) + 0.5 * math.sin(two_pi * f * 1.003 * t) + brightness * 0.3 * math.sin(two_pi * 2 * f * t)
        pad *= 0.12 * (0.85 + 0.15 * math.sin(two_pi * 0.25 * t))
        # arpeggio on 8th notes, plucked envelope
        step = int(t / (beat / 2))
        arp_f = root * 2 * (2 ** (chord[step % len(chord)] / 12))
        phase = (t % (beat / 2)) / (beat / 2)
        arp = brightness * 0.18 * math.exp(-4 * phase) * math.sin(two_pi * arp_f * t)
        # soft kick on each beat
        kp = (t % beat) / beat
        kick = 0.35 * math.exp(-18 * kp) * math.sin(two_pi * (55 + 40 * math.exp(-30 * kp)) * (t % beat))
        # master fade in/out
        env = min(1.0, t / 2.0, (seconds - t) / 4.0)
        out[i] = (pad + arp + kick) * env
    peak = max(1e-6, max(abs(x) for x in out))
    pcm = struct.pack(f"<{n}h", *(int(max(-1.0, min(1.0, x / peak * 0.85)) * 32767) for x in out))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def seed_admin(db) -> User:
    email = os.getenv("ADMIN_EMAIL", "admin@longform.local").lower()
    password = os.getenv("ADMIN_PASSWORD", "admin12345" if not settings.is_production else None)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        if not password:
            raise SystemExit("ADMIN_PASSWORD must be set to create the initial superuser in production")
        user = User(email=email, password_hash=hash_password(password), full_name="Administrator", is_superuser=True, is_verified=True)
        db.add(user)
        db.flush()
        sub = ensure_subscription_sync(db, user)
        apply_plan(sub, PlanTier.STUDIO)
        add_credits_sync(db, user, sub.monthly_credits, CreditTransactionKind.GRANT, description="Initial admin credits", reference=f"seed-admin:{user.id}")
        log.info("created superuser", email=email)
    else:
        log.info("superuser exists", email=email)
    return user


def seed_providers(db) -> int:
    n = 0
    for kind, infos in get_registry().available().items():
        for info in infos:
            row = db.execute(select(AIProvider).where(AIProvider.kind == ProviderKind(kind), AIProvider.name == info.name)).scalar_one_or_none()
            if row is None:
                row = AIProvider(kind=ProviderKind(kind), name=info.name, display_name=info.display_name)
                db.add(row)
            row.is_configured = info.is_configured
            row.default_model = info.default_model
            row.capabilities = {k: v for k, v in info.capabilities.items() if k != "active"}
            row.is_default = bool(info.capabilities.get("active"))
            n += 1
    db.flush()
    return n


def seed_music(db, owner: User) -> int:
    existing = {a.filename for a in db.execute(select(AudioAsset).where(AudioAsset.is_system.is_(True))).scalars()}
    created = 0
    for name, mood, bpm, prog, root, bright in MUSIC_BEDS:
        fname = f"{name.lower().replace(' ', '-')}.wav"
        if fname in existing:
            continue
        log.info("synthesising music bed", name=name)
        data = _synth_music(bpm, prog, root, bright)
        asset = save_audio_asset_sync(db, owner_id=owner.id, data=data, content_type="audio/wav", filename=fname, kind=AudioKind.MUSIC, source=MediaSource.SYSTEM, mood=mood, tags=["system", mood, f"{bpm}bpm"], is_system=True, license="CC0 - generated in-house")
        asset.bpm = bpm
        asset.extra = {"title": name, "generated": True}
        created += 1
    db.flush()
    return created


def main() -> None:
    with sync_session() as db:
        admin = seed_admin(db)
        n_prov = seed_providers(db)
        n_music = seed_music(db, admin)
        # make sure every user has a subscription row (older accounts)
        for u in db.execute(select(User)).scalars():
            if db.execute(select(Subscription).where(Subscription.user_id == u.id)).scalar_one_or_none() is None:
                ensure_subscription_sync(db, u)
    log.info("seed complete", providers=n_prov, music_created=n_music)


if __name__ == "__main__":
    main()

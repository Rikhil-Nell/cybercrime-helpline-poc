"""Voice persona and speech-recognition hints for the helpline desk."""

# Common Indian first name — easy to romanize in English STT, not tied to a real person.
AGENT_VOICE_NAME = "Kavita"

# Deepgram keyterms — improves recognition of India-specific acronyms and portal terms.
STT_KEYTERMS: list[str] = [
    "UPI",
    "OTP",
    "FIR",
    "IMPS",
    "NEFT",
    "RTGS",
    "BHIM",
    "PhonePe",
    "GPay",
    "Paytm",
    "Aadhaar",
    "PAN",
    "NCRP",
    "cybercrime.gov.in",
    "1930",
    "digital arrest",
    "sextortion",
    "UPI fraud",
    "Kavita",
]

# Common mis-hearings from phone audio → intended term (Deepgram replace map).
STT_REPLACE: dict[str, str] = {
    "uk fraud": "UPI fraud",
    "u k fraud": "UPI fraud",
    "you p i": "UPI",
    "you pee eye": "UPI",
    "o t p": "OTP",
    "one nine three zero": "1930",
}

# Phone lines need longer silence windows than web mic. STT-based turn detection
# (Deepgram utterance_end) is more reliable here than the multilingual EOU model.
TELEPHONY_TURN_HANDLING = {
    "turn_detection": "stt",
    "endpointing": {"min_delay": 0.4, "max_delay": 3.0},
}

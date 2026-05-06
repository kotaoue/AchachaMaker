"""Unit tests for the voicevox module."""

from unittest.mock import MagicMock, patch

import pytest

from src.voicevox import VoicevoxClient, LipSyncFrame


class TestVoicevoxClientIsAvailable:
    def test_returns_true_when_engine_running(self):
        client = VoicevoxClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("src.voicevox.requests.get", return_value=mock_resp):
            assert client.is_available() is True

    def test_returns_false_when_engine_not_running(self):
        import requests as req
        client = VoicevoxClient()
        with patch("src.voicevox.requests.get", side_effect=req.exceptions.ConnectionError):
            assert client.is_available() is False

    def test_returns_false_on_non_200(self):
        client = VoicevoxClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("src.voicevox.requests.get", return_value=mock_resp):
            assert client.is_available() is False


class TestCreateAudioQuery:
    def test_posts_to_audio_query_endpoint(self):
        client = VoicevoxClient(base_url="http://localhost:50021")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"accentPhrases": []}
        with patch("src.voicevox.requests.post", return_value=mock_resp) as mock_post:
            result = client.create_audio_query("こんにちは", speaker_id=1)
            mock_post.assert_called_once()
            url = mock_post.call_args[0][0]
            assert "/audio_query" in url
            assert result == {"accentPhrases": []}

    def test_raises_on_http_error(self):
        import requests as req
        client = VoicevoxClient()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.exceptions.HTTPError("404")
        with patch("src.voicevox.requests.post", return_value=mock_resp):
            with pytest.raises(req.exceptions.HTTPError):
                client.create_audio_query("test", speaker_id=1)


class TestSynthesize:
    def test_returns_wav_bytes(self):
        client = VoicevoxClient()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"RIFF\x00\x00\x00\x00WAVEfmt "
        with patch("src.voicevox.requests.post", return_value=mock_resp):
            result = client.synthesize({"accentPhrases": []}, speaker_id=1)
            assert result == mock_resp.content


class TestSynthesizeToFile:
    def test_writes_wav_to_path(self, tmp_path):
        client = VoicevoxClient()
        out = str(tmp_path / "speech.wav")
        wav_bytes = b"RIFF\x00\x00\x00\x00WAVEfmt "
        with patch.object(client, "create_audio_query", return_value={}):
            with patch.object(client, "synthesize", return_value=wav_bytes):
                result = client.synthesize_to_file("hello", speaker_id=1, output_path=out)
                assert result == out
                with open(out, "rb") as f:
                    assert f.read() == wav_bytes

    def test_creates_temp_file_when_no_path(self, tmp_path):
        client = VoicevoxClient()
        with patch.object(client, "create_audio_query", return_value={}):
            with patch.object(client, "synthesize", return_value=b"data"):
                with patch("src.voicevox.tempfile.mkstemp") as mock_mkstemp:
                    temp_file = str(tmp_path / "tmp.wav")
                    mock_mkstemp.return_value = (
                        open(temp_file, "wb").fileno(),
                        temp_file,
                    )
                    with patch("src.voicevox.os.close"):
                        result = client.synthesize_to_file("hello", speaker_id=1)
                        assert result == temp_file


class TestGetLipSyncFrames:
    def _make_query(self, moras: list) -> dict:
        return {
            "accentPhrases": [{"moras": moras, "pauseMora": None}],
            "prePhonemeLength": 0.0,
            "speedScale": 1.0,
        }

    def test_returns_list_of_lip_sync_frames(self):
        mora = {
            "text": "あ",
            "consonant": None,
            "consonantLength": None,
            "vowel": "a",
            "vowelLength": 0.1,
            "pitch": 5.0,
        }
        client = VoicevoxClient()
        frames = client.get_lip_sync_frames(self._make_query([mora]))
        assert isinstance(frames, list)
        assert all(isinstance(f, LipSyncFrame) for f in frames)

    def test_first_frame_is_closed(self):
        client = VoicevoxClient()
        frames = client.get_lip_sync_frames(self._make_query([]))
        assert frames[0].mouth_open == 0.0

    def test_last_frame_is_closed(self):
        mora = {
            "text": "あ",
            "consonant": None,
            "consonantLength": None,
            "vowel": "a",
            "vowelLength": 0.1,
            "pitch": 5.0,
        }
        client = VoicevoxClient()
        frames = client.get_lip_sync_frames(self._make_query([mora]))
        assert frames[-1].mouth_open == 0.0

    def test_vowel_a_has_full_openness(self):
        mora = {
            "text": "あ",
            "consonant": None,
            "consonantLength": None,
            "vowel": "a",
            "vowelLength": 0.15,
            "pitch": 5.0,
        }
        client = VoicevoxClient()
        frames = client.get_lip_sync_frames(self._make_query([mora]))
        open_frames = [f for f in frames if f.mouth_open > 0.9]
        assert len(open_frames) >= 1

    def test_pause_mora_closes_mouth(self):
        query = {
            "accentPhrases": [
                {
                    "moras": [],
                    "pauseMora": {
                        "text": "、",
                        "consonant": None,
                        "consonantLength": None,
                        "vowel": "pau",
                        "vowelLength": 0.2,
                        "pitch": 0.0,
                    },
                }
            ],
            "prePhonemeLength": 0.0,
            "speedScale": 1.0,
        }
        client = VoicevoxClient()
        frames = client.get_lip_sync_frames(query)
        # Should have a closed-mouth frame for the pause
        assert any(f.mouth_open == 0.0 for f in frames)

    def test_consonant_adds_closed_frame(self):
        mora = {
            "text": "か",
            "consonant": "k",
            "consonantLength": 0.05,
            "vowel": "a",
            "vowelLength": 0.1,
            "pitch": 5.0,
        }
        client = VoicevoxClient()
        frames = client.get_lip_sync_frames(self._make_query([mora]))
        # Should include at least one frame with mouth closed (consonant)
        closed = [f for f in frames if f.mouth_open == 0.0]
        assert len(closed) >= 1

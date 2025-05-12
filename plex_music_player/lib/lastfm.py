from typing import Optional, Dict, Any
import time
import hashlib
import requests
from plexapi.audio import Track
from ..lib.logger import Logger

logger = Logger()

class LastFMScrobbler:
    """Last.fm scrobbling integration."""
    
    def __init__(self):
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.session_key: Optional[str] = None
        self.username: Optional[str] = None
        self.enabled: bool = False  # Disabled by default
        self.scrobble_threshold: float = 0.5  # 50% of track duration
        self.min_scrobble_time: int = 240  # 4 minutes in seconds
        self._current_track: Optional[Track] = None
        self._track_start_time: float = 0
        self._track_played_time: int = 0
        self._scrobbled_tracks: set = set()  # Keep track of scrobbled tracks in current session
        self._last_scrobble_attempt: dict = {}  # track_id -> last attempt timestamp

    def get_session_key(self, token: str) -> str:
        """Get session key using the authentication token."""
        if not self.api_key or not self.api_secret:
            raise Exception("API Key and API Secret must be configured first")

        # Create the signature
        sig_data = {
            "api_key": self.api_key,
            "method": "auth.getSession",
            "token": token
        }
        
        # Sort parameters alphabetically
        sig_string = "".join(f"{k}{sig_data[k]}" for k in sorted(sig_data.keys()))
        sig_string += self.api_secret
        
        # Calculate MD5 hash
        sig = hashlib.md5(sig_string.encode()).hexdigest()
        
        # Add signature to parameters
        sig_data["api_sig"] = sig
        sig_data["format"] = "json"
        
        # Make the request
        response = requests.post("https://ws.audioscrobbler.com/2.0/", data=sig_data)
        data = response.json()
        
        if "session" in data:
            return data["session"]["key"]
        else:
            raise Exception(data.get("message", "Unknown error"))

    def configure(self, api_key: str, api_secret: str, username: str, session_key: str, enabled: bool = True) -> None:
        """Configure the Last.fm scrobbler."""
        self.api_key = api_key
        self.api_secret = api_secret
        self.username = username
        self.session_key = session_key
        self.enabled = enabled

    def _generate_signature(self, params: Dict[str, str]) -> str:
        # Exclude 'format' from signature parameters as required by Last.fm API
        params_for_sig = {k: v for k, v in params.items() if k != "format"}
        sorted_params = dict(sorted(params_for_sig.items()))
        sig_string = "".join(f"{k}{v}" for k, v in sorted_params.items())
        sig_string += self.api_secret
        return hashlib.md5(sig_string.encode()).hexdigest()

    def _make_request(self, method: str, params: Dict[str, str]) -> Dict[str, Any]:
        """Make a request to Last.fm API."""
        if not self.enabled or not self.session_key:
            return {}

        base_params = {
            "method": method,
            "api_key": self.api_key,
            "sk": self.session_key,
            "format": "json"
        }
        base_params.update(params)
        
        # Add signature
        base_params["api_sig"] = self._generate_signature(base_params)

        logger.debug(f"Last.fm API request: method={method}, params={base_params}")
        
        try:
            response = requests.post("https://ws.audioscrobbler.com/2.0/", data=base_params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Last.fm API request failed: {e}")
            return {}

    def update_now_playing(self, track: Track) -> None:
        """Update Now Playing status."""
        if not self.enabled or not track:
            return

        params = {
            "track": track.title,
            "artist": track.grandparentTitle if hasattr(track, "grandparentTitle") else "Unknown Artist",
            "album": track.parentTitle if hasattr(track, "parentTitle") else "Unknown Album",
            "duration": str(track.duration // 1000) if hasattr(track, "duration") else "0"
        }

        self._make_request("track.updateNowPlaying", params)
        self._current_track = track
        self._track_start_time = time.time()
        self._track_played_time = 0

    def scrobble(self, track: Track, played_time: int) -> None:
        """Scrobble a track."""
        if not self.enabled or not track:
            return

        track_id = f"{track.ratingKey}"
        if track_id in self._scrobbled_tracks:
            return

        # Check if enough time has passed since last attempt
        now = time.time()
        last_attempt = self._last_scrobble_attempt.get(track_id, 0)
        if now - last_attempt < 10:
            return
        self._last_scrobble_attempt[track_id] = now

        # Check if track meets scrobble criteria
        if not self._should_scrobble(track, played_time):
            return

        params = {
            "track": track.title,
            "artist": track.grandparentTitle if hasattr(track, "grandparentTitle") else "Unknown Artist",
            "album": track.parentTitle if hasattr(track, "parentTitle") else "Unknown Album",
            "timestamp": str(int(time.time())),
            "duration": str(track.duration // 1000) if hasattr(track, "duration") else "0"
        }

        result = self._make_request("track.scrobble", params)
        logger.debug(f"scrobble: response={result}")
        if str(result.get("scrobbles", {}).get("@attr", {}).get("accepted")) == "1":
            self._scrobbled_tracks.add(track_id)
            logger.info(f"Successfully scrobbled: {track.title}")

    def _should_scrobble(self, track: Track, played_time: int) -> bool:
        """Check if a track should be scrobbled based on play time and duration."""
        if not hasattr(track, "duration"):
            return played_time >= self.min_scrobble_time

        track_duration = track.duration // 1000  # Convert to seconds
        return (played_time >= track_duration * self.scrobble_threshold or 
                played_time >= self.min_scrobble_time)

    def update_playback_progress(self, position: int) -> None:
        """Update playback progress and scrobble if necessary."""
        if not self.enabled or not self._current_track:
            return

        self._track_played_time = position // 1000  # Convert to seconds
        if self._should_scrobble(self._current_track, self._track_played_time):
            self.scrobble(self._current_track, self._track_played_time)

    def clear_now_playing(self) -> None:
        """Clear Now Playing status."""
        if not self.enabled:
            return

        self._current_track = None
        self._track_start_time = 0
        self._track_played_time = 0
        self._scrobbled_tracks.clear() 
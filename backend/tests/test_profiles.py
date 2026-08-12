from __future__ import annotations

from cinevoice_api.profiles import list_profiles, load_profile


def test_all_profiles_validate() -> None:
    profiles = list_profiles()
    assert {item["id"] for item in profiles} == {"natural", "studio", "deep-narration"}
    for item in profiles:
        profile = load_profile(item["id"])
        assert profile["schema_version"] == 1
        assert profile["true_peak_ceiling_dbtp"] <= -0.1

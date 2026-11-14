import pytest

from nisar_hazard_watch.utils.gateway_layers import gateway_url, layer_kind, layer_title

BASE_URL = "https://gateway.example.test"


def test_a_gateway_path_becomes_an_absolute_gateway_url() -> None:
    # Arrange
    path = "/v2/cases/chokwe/layers/change_db_hh.png"

    # Act
    url = gateway_url(base_url=BASE_URL + "/", path=path)

    # Assert
    assert url == f"{BASE_URL}{path}"


@pytest.mark.parametrize(
    argnames="path",
    argvalues=["https://elsewhere.example.test/x.png", "//elsewhere.example.test/x.png"],
)
def test_a_url_on_another_host_is_refused(path: str) -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="not served by the ML gateway"):
        gateway_url(base_url=BASE_URL, path=path)


@pytest.mark.parametrize(
    argnames=("layer_id", "kind", "title"),
    argvalues=[
        ("display_baseline_change_HH", "change", "baseline change HH"),
        (
            "display_flood_signature_flags_dual_darkening",
            "diagnostic",
            "flood signature flags dual darkening",
        ),
        ("display_coherence_coherence", "coherence", "Interferometric coherence"),
        ("display_2026-08-28_HH", "observed", "2026-08-28 HH"),
        ("change_db_hh", "layer", "change db hh"),
    ],
)
def test_a_layer_id_names_its_kind_and_title(layer_id: str, kind: str, title: str) -> None:
    # Act / Assert
    assert (layer_kind(layer_id), layer_title(layer_id)) == (kind, title)

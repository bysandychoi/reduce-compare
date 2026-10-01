"""원본·축소본 공통 2D/3D 투영 테스트 (T053)."""
import numpy as np
import pytest
from sklearn.decomposition import PCA

from app.core.projection import project_comparison


def _matrices(seed=0):
    rng = np.random.default_rng(seed)
    original = rng.normal(size=(80, 5))
    reduced = original[[2, 8, 13, 21, 34, 55]]
    return original, reduced


@pytest.mark.parametrize("dimensions", [2, 3])
def test_pca_uses_one_coordinate_space(dimensions):
    original, reduced = _matrices()
    result = project_comparison(original, reduced, dimensions=dimensions)
    expected = PCA(n_components=dimensions, random_state=0).fit(original)

    assert result.original.shape == (80, dimensions)
    assert result.reduced.shape == (6, dimensions)
    assert np.allclose(result.reduced, expected.transform(reduced))


def test_original_subsample_is_reproducible_and_reduced_is_not_sampled():
    original, reduced = _matrices()
    first = project_comparison(original, reduced, seed=7, original_limit=20)
    second = project_comparison(original, reduced, seed=7, original_limit=20)

    assert len(first.original) == 20
    assert len(first.reduced) == len(reduced)
    assert np.array_equal(first.original_indices, second.original_indices)
    assert np.allclose(first.original, second.original)


@pytest.mark.parametrize("dimensions", [2, 3])
def test_umap_projects_both_inputs_with_requested_dimensions(dimensions):
    original, reduced = _matrices()
    result = project_comparison(original, reduced, method="UMAP", dimensions=dimensions, seed=3)

    assert result.method == "umap"
    assert result.original.shape == (80, dimensions)
    assert result.reduced.shape == (6, dimensions)
    assert np.isfinite(result.original).all()
    assert np.isfinite(result.reduced).all()


@pytest.mark.parametrize(
    ("original", "reduced", "message"),
    [
        (np.empty((0, 3)), np.ones((2, 3)), "원본 특징 행렬이 비어"),
        (np.ones((3, 2)), np.ones((2, 3)), "특징 수가 다릅니다"),
        (np.array([[1, 2], [3, np.nan]]), np.ones((2, 2)), "NaN 또는 무한대"),
    ],
)
def test_invalid_feature_matrices_are_rejected(original, reduced, message):
    with pytest.raises(ValueError, match=message):
        project_comparison(original, reduced)


def test_invalid_projection_options_are_rejected():
    original, reduced = _matrices()
    with pytest.raises(ValueError, match="투영 방식"):
        project_comparison(original, reduced, method="tsne")
    with pytest.raises(ValueError, match="차원은 2 또는 3"):
        project_comparison(original, reduced, dimensions=4)
    with pytest.raises(ValueError, match="PCA 투영 축 수"):
        project_comparison(np.ones((2, 5)), reduced, dimensions=3)
    with pytest.raises(ValueError, match="3D UMAP.*5개 이상"):
        project_comparison(np.ones((4, 5)), reduced, method="umap", dimensions=3)

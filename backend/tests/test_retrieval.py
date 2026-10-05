import numpy as np

from app.loaders import Segment
from app.retrieval import mmr, split


def test_split_keeps_page_numbers_and_numbers_chunks_in_order():
    long_page = " ".join(f"Sentence number {i} explains a detail." for i in range(40))
    chunks = split([Segment(long_page, 1), Segment("Short second page.", 2)], 200, 20)

    assert len(chunks) > 2
    assert all(len(chunk.text) <= 200 for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert chunks[-1].page == 2 and chunks[-1].text == "Short second page."
    assert {chunk.page for chunk in chunks[:-1]} == {1}


def test_mmr_skips_near_duplicates():
    query = np.array([1.0, 0.0])
    candidates = np.array([[1.0, 0.0], [0.99, 0.01], [0.6, 0.8]])
    assert mmr(query, candidates, k=2, diversity=0.7) == [0, 2]


def test_mmr_without_diversity_is_plain_relevance_order():
    query = np.array([1.0, 0.0])
    candidates = np.array([[0.6, 0.8], [1.0, 0.0], [0.99, 0.01]])
    assert mmr(query, candidates, k=3, diversity=0.0) == [1, 2, 0]


def test_mmr_handles_small_inputs():
    assert mmr(np.array([1.0, 0.0]), np.empty((0, 2)), k=3) == []
    assert mmr(np.array([1.0, 0.0]), np.array([[0.0, 1.0]]), k=5) == [0]

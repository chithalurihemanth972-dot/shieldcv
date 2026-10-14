"""ScanCancelled must stop every engine; other callback errors stay swallowed."""
from __future__ import annotations

import pytest

from helpers import DEMO
from src.utils.cancel import CancelToken, ScanCancelled


def _cancel(*_args, **_kwargs):
    raise ScanCancelled()


def test_token_lifecycle():
    token = CancelToken()
    assert not token.cancelled
    token.check()
    token.cancel()
    assert token.cancelled
    with pytest.raises(ScanCancelled):
        token.check()


def test_scan_cancelled_is_not_an_exception():
    assert issubclass(ScanCancelled, BaseException)
    assert not issubclass(ScanCancelled, Exception)


def test_data_scanner_propagates_cancel():
    from src.scanners.data_scanner import DataIntegrityEngine
    with pytest.raises(ScanCancelled):
        DataIntegrityEngine().scan(str(DEMO / "data" / "clean"), max_images=4,
                                   progress_callback=_cancel)


def test_model_auditor_propagates_cancel():
    from src.scanners.model_auditor import ModelIntegrityEngine
    with pytest.raises(ScanCancelled):
        ModelIntegrityEngine().audit(str(DEMO / "models" / "clean_model_scripted.pt"),
                                     run_neural_cleanse=False, progress_callback=_cancel)


def test_drift_detector_propagates_cancel():
    from src.scanners.drift_detector import DistributionShiftDetector
    with pytest.raises(ScanCancelled):
        DistributionShiftDetector().compare(str(DEMO / "data" / "clean"),
                                            str(DEMO / "data" / "poisoned"),
                                            max_images=4, progress_callback=_cancel)


def test_crypto_chain_propagates_cancel():
    from src.scanners.crypto_chain import InferenceProvenanceEngine
    with pytest.raises(ScanCancelled):
        InferenceProvenanceEngine().verify(str(DEMO / "records" / "clean_chain.json"),
                                           progress_callback=_cancel)


def test_agents_propagate_cancel():
    from src.agents.manager import OfficeManager
    with pytest.raises(ScanCancelled):
        OfficeManager().run(str(DEMO / "data" / "clean"), contributors=["contributor_alpha"],
                            max_images=4, parallel=False,
                            agent_progress=lambda *a: _cancel())


def test_other_callback_errors_are_still_swallowed():
    from src.scanners.crypto_chain import InferenceProvenanceEngine

    def broken(*_args):
        raise ValueError("ui exploded")

    result = InferenceProvenanceEngine().verify(str(DEMO / "records" / "clean_chain.json"),
                                                progress_callback=broken)
    assert result["num_records"] > 0

"""Compatibility shim for old import style"""
try:
    from .boardreader import BoardReaderEngine
except ImportError:
    from brute.engines.boardreader import BoardReaderEngine

# Alias for compatibility
ExactPhraseRecallRunnerBoardreaderV2 = BoardReaderEngine
BoardReaderSearch = BoardReaderEngine

__all__ = ['BoardReaderEngine', 'ExactPhraseRecallRunnerBoardreaderV2', 'BoardReaderSearch']

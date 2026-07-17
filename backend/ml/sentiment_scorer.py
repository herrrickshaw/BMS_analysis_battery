"""
Sentiment scorer for financial news articles.

Data sources (in priority order):
  1. Financial Sentiment Lexicon (Kaggle) — 580+ financial terms, -1 to +1
  2. Labelled Financial News (Kaggle: ankurzing) — pos/neg/neutral labels
  3. Finance News Sentiments (Kaggle: antobenedetti) — 32k+ labelled articles
  4. Stock Tweets (Kaggle: equinxx) — social sentiment
  5. Built-in mini-lexicon — always available as fallback

Scoring:
  - Lexicon: tokenise headline+description, average matched term scores
  - ML model: optional scikit-learn TF-IDF + LogisticRegression trained on
    the labelled datasets; auto-trained on first load if sklearn is installed
  - Final score: ML score if model trained, else lexicon score
  - Output range: -1.0 (very bearish) to +1.0 (very bullish)
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── built-in mini-lexicon (always available) ──────────────────────────────────
_MINI_LEXICON: dict[str, float] = {
    # Bullish
    'surge': 0.8, 'rally': 0.8, 'soar': 0.9, 'jump': 0.7, 'gain': 0.6,
    'rise': 0.5, 'boost': 0.6, 'beat': 0.7, 'profit': 0.6, 'growth': 0.6,
    'record': 0.5, 'strong': 0.6, 'upgrade': 0.7, 'bullish': 0.9,
    'outperform': 0.7, 'buy': 0.5, 'positive': 0.5, 'optimistic': 0.6,
    'breakthrough': 0.7, 'acquisition': 0.4, 'dividend': 0.4, 'revenue': 0.3,
    'expansion': 0.5, 'recovery': 0.6, 'rebound': 0.7, 'upside': 0.6,
    # Bearish
    'crash': -0.9, 'plunge': -0.9, 'tumble': -0.8, 'fall': -0.6,
    'drop': -0.6, 'decline': -0.6, 'loss': -0.7, 'miss': -0.6,
    'weak': -0.6, 'downgrade': -0.7, 'bearish': -0.9, 'sell': -0.5,
    'negative': -0.5, 'concern': -0.4, 'risk': -0.3, 'warning': -0.7,
    'layoff': -0.7, 'lawsuit': -0.6, 'fraud': -0.9, 'bankrupt': -0.9,
    'debt': -0.4, 'recession': -0.8, 'inflation': -0.3, 'default': -0.8,
    'downside': -0.6, 'investigation': -0.5, 'penalty': -0.6, 'fine': -0.5,
}

_KAGGLE_DIR = Path(__file__).parent.parent.parent / 'data' / 'kaggle' / 'sentiment'


class SentimentScorer:
    def __init__(self):
        self._lexicon: dict[str, float] = dict(_MINI_LEXICON)
        self._model = None          # optional sklearn pipeline
        self._datasets_loaded: list[str] = []

    # ── public API ─────────────────────────────────────────────────────────────

    def score(self, text: str) -> float:
        """Return sentiment score in [-1, +1]. Positive = bullish."""
        if not text:
            return 0.0
        if self._model is not None:
            try:
                return float(self._model.predict_proba([text])[0][2]) - \
                       float(self._model.predict_proba([text])[0][0])
            except Exception:
                pass
        return self._lexicon_score(text)

    def label(self, score: float) -> str:
        if score > 0.15:
            return 'bullish'
        if score < -0.15:
            return 'bearish'
        return 'neutral'

    def annotate(self, text: str) -> dict:
        s = self.score(text)
        return {'sentiment_score': round(s, 3), 'sentiment_label': self.label(s)}

    @property
    def loaded_datasets(self) -> list[str]:
        return list(self._datasets_loaded)

    # ── loaders ────────────────────────────────────────────────────────────────

    def load_all(self) -> None:
        """Load all available Kaggle datasets from data/kaggle/sentiment/."""
        self._load_lexicon()
        self._load_labelled_datasets()
        log.info('SentimentScorer ready — lexicon: %d terms, model: %s, datasets: %s',
                 len(self._lexicon), 'trained' if self._model else 'none',
                 self._datasets_loaded or ['mini-lexicon only'])

    def _load_lexicon(self) -> None:
        """Load Financial Sentiment Lexicon (580+ terms)."""
        import glob
        pattern = str(_KAGGLE_DIR / 'financial-sentiment-lexicon' / '*.csv')
        files = glob.glob(pattern)
        if not files:
            log.info('Sentiment lexicon not found at %s — using mini-lexicon', pattern)
            return
        try:
            import pandas as pd
            df = pd.read_csv(files[0])
            # Try common column name patterns
            word_col = next((c for c in df.columns if 'word' in c.lower() or 'term' in c.lower() or 'phrase' in c.lower()), df.columns[0])
            score_col = next((c for c in df.columns if 'score' in c.lower() or 'sentiment' in c.lower()), df.columns[1])
            for _, row in df.iterrows():
                word = str(row[word_col]).lower().strip()
                try:
                    score = float(row[score_col])
                    if -1.0 <= score <= 1.0 and word:
                        self._lexicon[word] = score
                except (ValueError, TypeError):
                    pass
            self._datasets_loaded.append('financial-sentiment-lexicon')
            log.info('Loaded sentiment lexicon: %d terms (from %s)', len(self._lexicon), files[0])
        except Exception as exc:
            log.warning('Failed to load sentiment lexicon: %s', exc)

    def _load_labelled_datasets(self) -> None:
        """Train a simple ML model on the labelled news datasets."""
        try:
            from sklearn.pipeline import Pipeline
            from sklearn.linear_model import LogisticRegression
            from sklearn.feature_extraction.text import TfidfVectorizer
            import pandas as pd
        except ImportError:
            log.info('scikit-learn not installed — skipping ML sentiment model')
            return

        texts, labels = [], []
        label_map = {
            'positive': 2, 'pos': 2, '1': 2, 1: 2,
            'neutral': 1, 'neu': 1, '0': 1, 0: 1,
            'negative': 0, 'neg': 0, '-1': 0, -1: 0,
        }

        # Dataset 1: ankurzing/sentiment-analysis-for-financial-news
        self._load_labelled_csv(
            _KAGGLE_DIR / 'labelled-financial-news',
            text_cols=['News Headline', 'Sentence', 'text', 'headline', 'news'],
            label_cols=['Sentiment', 'sentiment', 'label'],
            label_map=label_map,
            texts=texts, labels=labels,
            name='labelled-financial-news',
        )

        # Dataset 2: antobenedetti/finance-news-sentiments (32k+)
        self._load_labelled_csv(
            _KAGGLE_DIR / 'finance-news-sentiments',
            text_cols=['title', 'text', 'news', 'headline', 'content'],
            label_cols=['sentiment', 'label', 'Sentiment'],
            label_map=label_map,
            texts=texts, labels=labels,
            name='finance-news-sentiments',
        )

        # Dataset 3: stock tweets
        self._load_labelled_csv(
            _KAGGLE_DIR / 'stock-tweets',
            text_cols=['Tweet', 'tweet', 'text', 'content'],
            label_cols=['Sentiment', 'sentiment', 'label'],
            label_map=label_map,
            texts=texts, labels=labels,
            name='stock-tweets',
        )

        if len(texts) < 100:
            log.info('Not enough labelled data for ML model (%d samples)', len(texts))
            return

        log.info('Training sentiment model on %d labelled samples...', len(texts))
        try:
            pipe = Pipeline([
                ('tfidf', TfidfVectorizer(max_features=20_000, ngram_range=(1, 2),
                                          sublinear_tf=True)),
                ('clf', LogisticRegression(max_iter=500, C=1.0, class_weight='balanced')),
            ])
            pipe.fit(texts, labels)
            self._model = pipe
            log.info('Sentiment ML model trained successfully')
        except Exception as exc:
            log.warning('ML model training failed: %s', exc)

    def _load_labelled_csv(
        self, directory: Path,
        text_cols: list[str], label_cols: list[str], label_map: dict,
        texts: list, labels: list, name: str,
    ) -> None:
        import glob
        import pandas as pd
        files = glob.glob(str(directory / '*.csv'))
        if not files:
            return
        for fpath in files:
            try:
                df = pd.read_csv(fpath, encoding='utf-8', errors='replace', low_memory=False)
                text_col = next((c for c in text_cols if c in df.columns), None)
                label_col = next((c for c in label_cols if c in df.columns), None)
                if not text_col or not label_col:
                    continue
                for _, row in df.iterrows():
                    raw_label = str(row[label_col]).strip().lower()
                    mapped = label_map.get(raw_label) or label_map.get(row[label_col])
                    if mapped is not None and str(row[text_col]).strip():
                        texts.append(str(row[text_col]).strip())
                        labels.append(mapped)
                if name not in self._datasets_loaded:
                    self._datasets_loaded.append(name)
                log.info('Loaded labelled dataset %s: +%d samples', name, len(texts))
                break
            except Exception as exc:
                log.warning('Failed to load %s: %s', fpath, exc)

    # ── internals ──────────────────────────────────────────────────────────────

    def _lexicon_score(self, text: str) -> float:
        tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower())
        scores = [self._lexicon[t] for t in tokens if t in self._lexicon]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 3)


# Global singleton — call scorer.load_all() at startup
scorer = SentimentScorer()

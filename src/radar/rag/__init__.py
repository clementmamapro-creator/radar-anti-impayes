"""Assistant « impayés » : RAG juridique sourcé et évalué.

1. `legi` construit le corpus à partir de l'export officiel LEGI (Légifrance, DILA).
2. `index` retrouve les articles pertinents (BM25, adapté au français).
3. `assistant` fait rédiger la réponse par un LLM, uniquement à partir des
   articles retrouvés, en les citant.
4. `evaluation` mesure la qualité de la recherche sur un jeu de questions.
"""

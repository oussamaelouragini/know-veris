# Cahier des charges — KnowVeris IA

> Assistant IA interne pour employés de banque — système RAG (Retrieval-Augmented
> Generation) 100 % self-hosted, multilingue FR / EN / AR.
>
> Document de référence fonctionnel (branche descendante du Cycle en V). Pour
> l'architecture et le planning détaillés, voir [PLAN.md](../PLAN.md) ; pour le
> contexte technique quotidien, voir [docs.md](../docs.md).

| | |
|---|---|
| **Projet** | KnowVeris IA |
| **Type** | Stage de fin d'études — 4 semaines, une personne |
| **Version** | 1.0 — Semaine 0 |
| **Statut** | Périmètre figé |

---

## 1. Contexte

Les employés de la banque (conformité, KYC, crédit, opérations) recherchent
manuellement l'information dans des dizaines de procédures internes au format PDF
et DOCX. Ce processus est **lent**, **source d'erreurs**, et **sans traçabilité** :
rien ne garantit que la réponse trouvée provient bien de la version en vigueur du
bon document.

**KnowVeris** répond à ce besoin : un employé authentifié pose une question en
langage naturel et obtient une réponse générée **uniquement** à partir des
documents internes indexés, avec **citation exacte de la source** (document + page
pour les PDF, document + section pour les DOCX).

---

## 2. Objectifs

### 2.1 Objectif général

Fournir un assistant conversationnel interne, fiable et traçable, qui réduit le
temps de recherche documentaire tout en garantissant que chaque réponse est
**ancrée dans une source vérifiable** et qu'**aucune donnée ne quitte la machine**.

### 2.2 Objectifs mesurables (critères de recette)

| Réf. | Objectif | Cible |
|---|---|---|
| KPI-1 | La bonne source figure dans le top-3 retourné | Recall@3 > 85 % |
| KPI-2 | Refus correct sur une question hors corpus | > 90 % |
| KPI-3 | Faux refus sur une question dont la réponse est dans le corpus | < 10 % |
| KPI-4 | Réponse rendue dans la langue de la question (FR/EN/AR) | 100 % |
| KPI-5 | Chaque réponse porte au moins une citation vérifiable | 100 % |
| KPI-6 | Latence de bout en bout (CPU-only) | < 90 s |

Ces cibles sont mesurées sur le **golden set** d'évaluation (semaine 2), pas
appréciées « à l'œil ».

---

## 3. Périmètre

### 3.1 Inclus

- Authentification des employés via Keycloak (OIDC + PKCE), rôles `employee` / `admin`.
- Question-réponse en langage naturel sur le corpus documentaire interne.
- Réponses **sourcées** avec citation exacte (document + page / section) et score.
- Support **multilingue FR / EN / AR** avec détection automatique de la langue.
- Streaming SSE de la réponse (perception de réactivité malgré la latence CPU).
- Historique des conversations par utilisateur.
- Administration documentaire : upload, liste, statut d'indexation, suppression.
- Administration des comptes employés via l'API Admin de Keycloak.
- Journal d'audit des actions sensibles.

### 3.2 Exclu

- Aucune API d'IA externe (OpenAI, Google, Anthropic…) — contrainte structurante.
- Pas d'inscription libre (registration Keycloak **désactivée**) — comptes créés par un admin.
- Pas de modification / rédaction de documents par l'assistant (lecture seule du corpus).
- Pas d'entraînement ni de fine-tuning de modèle (modèles pré-entraînés uniquement).
- Query rewriting multi-tours par LLM — reporté en « perspectives d'évolution »
  (coût CPU inacceptable ; une version économe sans appel LLM est prévue en option).

---

## 4. Acteurs

| Acteur | Rôle | Droits |
|---|---|---|
| **Employé** (`employee`) | Utilisateur final | Se connecter, poser des questions, consulter ses conversations |
| **Administrateur** (`admin`) | Gestion du système | Tous droits employé + gérer les documents et les comptes employés |
| **Système** | Automatismes | Ingestion, indexation, audit, provisioning JIT des utilisateurs |

L'identité est **possédée par Keycloak** ; PostgreSQL ne fait que refléter
l'utilisateur via `keycloak_sub` (provisioning Just-In-Time à la première connexion).
Aucun mot de passe n'est stocké côté application.

---

## 5. Besoins fonctionnels

### 5.1 Authentification et autorisation

| Réf. | Besoin |
|---|---|
| EF-01 | Un employé s'authentifie via Keycloak (OIDC + PKCE) avant tout accès. |
| EF-02 | L'inscription libre est désactivée ; seuls les comptes créés par un admin existent. |
| EF-03 | L'accès aux fonctions d'administration est réservé au rôle `admin` (RBAC). |
| EF-04 | Le JWT est validé côté API via JWKS (signature, expiration, audience). |
| EF-05 | À la première connexion, l'utilisateur est provisionné en base (JIT) depuis son `sub` Keycloak. |
| EF-06 | La session expirée est gérée proprement côté front (ré-authentification). |

### 5.2 Question-réponse (cœur RAG)

| Réf. | Besoin |
|---|---|
| EF-07 | L'employé pose une question en langage naturel (FR, EN ou AR). |
| EF-08 | Le système détecte la langue de la question et **répond dans cette même langue**. |
| EF-09 | La réponse est générée **uniquement** à partir des documents indexés (pas de connaissance externe). |
| EF-10 | Chaque réponse cite au moins une source : document + page (PDF) ou document + section (DOCX). |
| EF-11 | Les citations affichées portent un score de pertinence et sont vérifiables par l'utilisateur. |
| EF-12 | Si aucune source ne dépasse le seuil de pertinence, le système **refuse de répondre** plutôt que d'inventer. |
| EF-13 | Après génération, chaque citation `[Sx]` produite est validée comme présente dans le contexte fourni ; sinon elle est retirée. |
| EF-14 | La réponse est **streamée** (SSE) au fur et à mesure de sa génération. |
| EF-15 | Les messages en arabe sont rendus en `dir="rtl"` (détection au niveau du message, pas de la page). |

### 5.3 Conversations

| Réf. | Besoin |
|---|---|
| EF-16 | Les questions, réponses et citations sont persistées par conversation et par utilisateur. |
| EF-17 | L'employé consulte l'historique de ses conversations. |
| EF-18 | *(Option)* Suivi multi-tours économe : fusion textuelle de la question précédente pour le retrieval, sans appel LLM supplémentaire, derrière un feature flag. |

### 5.4 Administration documentaire (rôle admin)

| Réf. | Besoin |
|---|---|
| EF-19 | L'admin téléverse un ou plusieurs documents (PDF, DOCX). |
| EF-20 | Le document est parsé, découpé (chunking), embarqué (BGE-M3) et indexé automatiquement. |
| EF-21 | Chaque chunk conserve sa métadonnée de source (`document_id` + `page_number` **ou** `section_title`). Un chunk sans source est un bug. |
| EF-22 | L'admin consulte la liste des documents et leur **statut d'indexation** (machine à états). |
| EF-23 | L'admin supprime un document ; ses chunks et vecteurs sont supprimés en cascade. |

### 5.5 Administration des comptes (rôle admin)

| Réf. | Besoin |
|---|---|
| EF-24 | L'admin crée un compte employé via l'API Admin REST de Keycloak (service account). |
| EF-25 | Un mot de passe temporaire est affiché **une seule fois** à la création. |
| EF-26 | L'admin liste et gère les comptes employés. |

### 5.6 Traçabilité

| Réf. | Besoin |
|---|---|
| EF-27 | Les actions sensibles (upload, suppression, gestion de comptes) sont journalisées (`audit_logs`). |

---

## 6. Besoins non fonctionnels

| Réf. | Besoin |
|---|---|
| ENF-01 | **Self-hosted strict** : aucune donnée ne quitte la machine ; aucune API externe pour l'embedding ou la génération. |
| ENF-02 | **CPU-only** : cible AMD Ryzen 7 4700U, 16 Go RAM, pas de GPU. Budget RAM ≈ 14 Go. |
| ENF-03 | **Latence** de bout en bout < 90 s par réponse (60-75 s attendus avec Qwen3 4B), streaming obligatoire pour la perception. |
| ENF-04 | **Multilingue FR/EN/AR** : détection automatique, pas de traduction, pas de langue imposée. |
| ENF-05 | **Licences libres uniquement** (Apache 2.0 / MIT) pour tous les modèles. |
| ENF-06 | **Sécurité** : aucun secret dans le code (tout via `.env`) ; aucun mot de passe applicatif ; JWT validé systématiquement. |
| ENF-07 | **Reproductibilité** : tout l'environnement se lève avec un seul `docker compose up` ; realm Keycloak versionné en JSON. |
| ENF-08 | **Traçabilité (Cycle en V)** : chaque besoin est traçable jusqu'à un test de validation. |
| ENF-09 | **`temperature = 0`** en génération, toujours (déterminisme des réponses). |
| ENF-10 | **Maintenabilité** : endpoints sans logique métier (délégation à `services/`), migrations via Alembic uniquement, type hints obligatoires. |

---

## 7. Contraintes techniques

Le matériel cible étant **CPU-only**, le goulot d'étranglement est le **prefill**
(ingestion du contexte par le modèle), pas la génération. Conséquences retenues :

- `chunk_size = 500` tokens, `overlap = 80`.
- `top_k = 3` après rerank (20 candidats récupérés, 3 conservés).
- `num_ctx = 4096` explicite ; system prompt **stable** pour profiter du prefix caching.
- Reranker BGE-reranker-v2-m3 derrière feature flag (coût 3-8 s sur CPU).
- Embeddings **BGE-M3 via Ollama** (pas de modèle résident dans le process FastAPI).

La pile technique complète est décrite dans [docs.md](../docs.md) ; les décisions
structurantes sont argumentées en ADR dans [docs/adr/](adr/).

---

## 8. Livrables

| Livrable | Échéance |
|---|---|
| Environnement reproductible (`docker compose up`) + ce cahier des charges | Semaine 0 |
| `specifications-fonctionnelles.md` | Semaine 0-1 |
| `specifications-techniques.md` | Semaine 1 |
| Walking skeleton (login → question → réponse sourcée) | Semaine 1 |
| API complète, testée et **mesurée** (Recall@3, taux de refus) | Semaine 2 |
| `plan-de-tests.md` + golden set (~35 Q/R) | Semaine 2 |
| Application frontend complète et démontrable | Semaine 3 |
| `PV-de-recette.md`, rapport, soutenance | Semaine 4 |
| ADR (`docs/adr/`) | Au fil de l'eau |

---

## 9. Planning (synthèse)

| Phase | Contenu | Point de contrôle |
|---|---|---|
| **S0** | Préparation : Docker Compose, Keycloak, modèles Ollama, corpus bootstrap | Environnement reproductible |
| **S1** | Fondations + walking skeleton vertical end-to-end | Un employé se connecte et obtient une réponse citée |
| **S2** | Qualité RAG (hybrid search, reranker, guardrails) + API complète | Recall@3 et taux de refus mesurés |
| **S3** | Frontend (chat streaming, sources, admin, RTL) | Application démontrable de bout en bout |
| **S4** | Rapport, soutenance, marge | Démo répétée + vidéo de secours |

Méthodologie : **Cycle en V à réalisation itérative** (3 itérations courtes en
S1-S2-S3, chacune close par son niveau de test). Détail dans [PLAN.md](../PLAN.md).

---

## 10. Hypothèses et risques

| Risque | Impact | Mitigation |
|---|---|---|
| Latence CPU trop élevée | Démo pénible | Streaming SSE ; contexte court ; benchmark modèle dès S1 ; vidéo de secours |
| Config FTS `arabic` absente de Postgres | Recherche AR dégradée | Fallback sur `simple` (pas de stemming) ; le vecteur BGE-M3 porte la charge |
| Corpus arabe de qualité introuvable | Exigence AR non démontrable | GAFI/FATF publie ses 40 Recommandations en AR — identifié, à télécharger en S0 |
| Absence de corpus réel (confidentialité) | Démo bloquée | Corpus **bootstrap** synthétique (S0) + corpus **démo** public (GAFI, ACPR, BCBS) collecté en parallèle |
| Retard planning (une personne, 4 semaines) | Périmètre non tenu | Walking skeleton en S1 (purge des risques d'intégration) ; buffer en S4 |

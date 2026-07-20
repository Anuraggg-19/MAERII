---
title: "Raw Material Knowledge Engine"
subtitle: "Data Dictionary and Schema Reference"
date: "June 22, 2026"
author: "MAERII Project Team"
toc: false
numbersections: true
geometry: margin=1in
fontsize: 11pt
mainfont: "Times New Roman"
colorlinks: false
---

\pagenumbering{gobble}
\definecolor{reportblue}{RGB}{32,72,132}
\begin{center}
\vspace*{1.15in}
{\Huge\bfseries\textcolor{reportblue}{Raw Material Knowledge Engine}\par}
\vspace{0.35in}
{\LARGE Data Dictionary and Schema Reference\par}
\vspace{0.25in}
{\large MAERII: Market Alignment Engine for Rural and Indigenous Innovation\par}
\vspace{0.55in}
{\large June 22, 2026\par}
\vspace{0.75in}
\end{center}

| Report Attribute | Details |
|---|---|
| Document Number | 02 |
| Document Type | Data Dictionary and Schema Reference |
| Project Module | Tribal Raw Material Knowledge Engine |
| Primary Dataset | `data/enriched_mfp_data.json` |
| Supporting Datasets | `data/deep_enrichment_evidence.json`, `data/material_relationships.json` |
| Scope | Field definitions, source locations, evidence model, LLM extraction behavior, and relationship construction |
| Prepared By | MAERII Project Team |

\vfill

\begin{center}
{\small This document provides the schema-level reference for the MAERII Raw Material Knowledge Engine. It explains how the dataset is structured, where values come from, how evidence is stored, and how graph relationships are built.}
\end{center}

\newpage
\pagenumbering{roman}

# Table of Contents

\tableofcontents

\newpage
\pagenumbering{arabic}

# Purpose of This Document

This document is the formal data dictionary and schema reference for the Raw Material Knowledge Engine. It is intended to explain the structure of the dataset in enough detail that a reviewer, developer, mentor, or future MAERII module owner can understand exactly what each file contains, what each field means, where the data came from, and how the system converts unstructured source material into structured records.

The first technical report explains the overall system architecture and project outcomes. This second document focuses on the dataset itself. It describes the canonical material schema, the deep enrichment schema, the evidence schema, the relationship edge schema, the source classification model, and the LLM's role in extraction.

The most important principle in this data model is traceability. The system does not treat the LLM as the final authority. Instead, the LLM is used as an extraction assistant over retrieved source text. Extracted values are stored with confidence scores and are linked to source evidence wherever possible.

# Dataset Inventory

The Raw Material Knowledge Engine uses one canonical item dataset and several supporting sidecar files. The canonical dataset stores the material records. The sidecar files store evidence, graph relationships, validation summaries, source traces, and run artifacts.

| File Location | Approx. Size | Role |
|---|---:|---|
| `data/enriched_mfp_data.json` | 280 KB | Canonical enriched MFP item dataset |
| `data/deep_enrichment_evidence.json` | 747 KB | Evidence store keyed by `evidence_id` |
| `data/material_relationships.json` | 313 KB | Graph-ready relationship edge list |
| `data/seed_mfp_list.json` | 41 KB | Cleaned seed records derived from the original MFP CSV |
| `data/enrichment_log.json` | 53 KB | Validation report for the base enrichment run |
| `data/enrichment_sources.json` | 20 KB | Source tracking from the base enrichment stage |
| `data/deep_enrichment_runs/` | Variable | Run manifests, previews, and validation outputs for deep enrichment |
| `data/backups/` | Variable | Pre-apply snapshots used for rollback |

The current dataset statistics are summarized below.

| Metric | Value |
|---|---:|
| Seed MFP records | 87 |
| Canonical enriched records | 87 |
| Records with `deep_enrichment` block | 86 |
| Evidence records | 1,502 |
| Relationship edges | 1,259 |
| Fully complete base records | 66 |
| Average base completeness | 96 percent |
| Base records needing review | 72 |

# Data Construction Overview

The complete dataset is built through two related enrichment paths: base enrichment and deep enrichment.

Base enrichment creates the core material profile. It begins with the TRIFED MFP seed list and adds fields such as scientific name, description, season, shelf life, states, artisan types, current products, potential products, image URL, and confidence values.

Deep enrichment extends the existing record without rewriting it. It adds a nested `deep_enrichment` object to the canonical item record and writes full source provenance to sidecar files. The deep enrichment path targets availability, quantities, districts, clusters, source evidence, and graph relationships.

The data construction flow is shown below.

| Stage | Source | System Action | Output |
|---|---|---|---|
| Seed preparation | `MFP_List_87_Items_Split.csv` | Parse CSV, normalize MSP, expand category codes, clean scientific names | `seed_mfp_list.json` |
| Base search | Serper web and image search | Generate field-specific search queries for each material | Search result snippets and URLs |
| Base fetching | HTML pages | Fetch and sanitize page text | Aggregated source text |
| Base LLM extraction | Aggregated source text | Extract base fields as strict JSON | Base enriched item fields |
| Base validation | Enriched item records | Check missing fields, confidence, and structural issues | `enrichment_log.json` |
| Deep search | Existing enriched records | Search for quantity, geography, and relationship evidence | Ranked source list |
| Deep fetching | HTML and PDF documents | Extract text from webpages and PDFs | Source dossier |
| Deep LLM extraction | Source dossier | Extract availability and geography only | `deep_enrichment` patch |
| Evidence modeling | Extracted values and source snippets | Create deterministic evidence IDs | `deep_enrichment_evidence.json` |
| Relationship modeling | Existing fields plus deep geography | Build graph-ready edges | `material_relationships.json` |

# Canonical Dataset Schema

The canonical dataset is stored at `data/enriched_mfp_data.json`. It is a JSON array. Each object represents one Minor Forest Produce material.

The record contains both original seed attributes and enriched attributes. Deep enrichment is stored as a nested object named `deep_enrichment`. Existing top-level fields remain the protected baseline.

## Canonical Record Shape

```json
{
  "mfp_id": 1,
  "name": "Tamarind (with seeds)",
  "scientific_name": "Tamarindus indica",
  "category": "Forest Produce",
  "msp": 36.0,
  "unit": "kg",
  "msp_notes": null,
  "applicability_raw": "All India",
  "states": ["Tamil Nadu", "Madhya Pradesh"],
  "description": "Concise material description...",
  "season": "March-April",
  "shelf_life": "9-12 months",
  "artisan_types": ["Fruit Collector"],
  "current_products": ["pulp", "powder"],
  "potential_products": ["seed derivatives"],
  "image_url": "https://example.com/image.jpg",
  "confidence": {
    "description": 0.9,
    "states": 0.8
  },
  "deep_enrichment": {
    "version": "v1",
    "status": "partial"
  }
}
```

## Base Field Dictionary

| Field | Type | Required | Description | Example |
|---|---|---:|---|---|
| `mfp_id` | integer | Yes | Stable numeric identifier assigned during seed parsing. | `1` |
| `name` | string | Yes | Common name of the MFP item from the source list. | `Tamarind (with seeds)` |
| `scientific_name` | string or null | No | Botanical or scientific name, cleaned during seed preparation or enriched by LLM. | `Tamarindus indica` |
| `category` | string | Yes | Expanded category derived from source category codes. | `Forest Produce` |
| `msp` | number or null | No | Minimum Support Price value parsed from the source list. | `36.0` |
| `unit` | string | Yes | Unit associated with MSP, generally kilograms. | `kg` |
| `msp_notes` | string or null | No | Notes for complex MSP values that cannot be represented as a single number. | `3200 / 1500 (per Thousand)` |
| `applicability_raw` | string | Yes | Original applicability text from the seed source before normalization. | `All India` |
| `states` | array of strings | No | Indian states where the material is known or inferred to be collected or available. | `["Tamil Nadu", "Madhya Pradesh"]` |
| `description` | string or null | No | Concise description of the material and its relevance. | `Tamarind is a leguminous tree...` |
| `season` | string or null | No | Harvesting or collection season, preferably expressed as months. | `March-April` |
| `shelf_life` | string or null | No | Storage duration in short duration format. | `9-12 months` |
| `artisan_types` | array of strings | No | Types of collectors, processors, or artisans associated with the material. | `["Fruit Collector", "Seed Collector"]` |
| `current_products` | array of strings | No | Products already made from the material. | `["pulp", "powder"]` |
| `potential_products` | array of strings | No | Higher-value or future value-added product possibilities. | `["seed derivatives"]` |
| `image_url` | string or null | No | Representative image URL retrieved through image search. | `https://...` |
| `confidence` | object | No | Field-level confidence values for base enrichment. | `{"description": 0.9}` |
| `deep_enrichment` | object | No | Additive deep enrichment block for supply intelligence and graph support. | See Section 5 |

## Base Field Coverage

| Field | Coverage |
|---|---:|
| `scientific_name` | 85 / 87 |
| `description` | 87 / 87 |
| `season` | 77 / 87 |
| `shelf_life` | 72 / 87 |
| `states` | 85 / 87 |
| `artisan_types` | 87 / 87 |
| `current_products` | 87 / 87 |
| `potential_products` | 81 / 87 |
| `image_url` | 87 / 87 |

# Deep Enrichment Schema

The `deep_enrichment` object is an additive extension inside each canonical material record. It is designed to store extra supply-side intelligence without changing the base record.

The deep enrichment block captures four major concepts:

- availability and quantity signals
- granular geography, especially districts and clusters
- relationship summaries for downstream modules
- evidence references and confidence values

## Deep Enrichment Record Shape

```json
{
  "version": "v1",
  "status": "partial",
  "availability": {
    "band": "medium",
    "quantity_records": [
      {
        "value": 250000,
        "unit": "tonnes",
        "year": null,
        "scope": "annual production",
        "metric_type": "production"
      }
    ]
  },
  "geography": {
    "districts": [],
    "clusters": []
  },
  "relationship_summary": {
    "related_regions": ["Tamil Nadu", "Madhya Pradesh"],
    "related_products": ["pulp", "powder"],
    "related_skills": ["Fruit Collector"],
    "related_material_groups": ["Forest Produce"]
  },
  "confidence": {
    "availability": 0.7,
    "geography": 0.0,
    "relationships": 1.0
  },
  "evidence_refs": ["evi_363051b04e7b5c30"],
  "last_updated_at": "2026-06-21T08:38:25Z"
}
```

## Deep Enrichment Field Dictionary

\begingroup
\small
\setlength{\tabcolsep}{4pt}
\renewcommand{\arraystretch}{1.2}
\begin{longtable}{p{0.31\textwidth} p{0.18\textwidth} p{0.43\textwidth}}
\textbf{Field} & \textbf{Type} & \textbf{Description} \\
\hline
\texttt{version} & string & Schema version for deep enrichment. Current value is \texttt{v1}. \\
\texttt{status} & string & Processing status. Expected values include \texttt{not\_started}, \texttt{partial}, \texttt{complete}, and \texttt{failed}. \\
\texttt{availability} & object & Availability intelligence, including a broad availability band and optional numeric records. \\
\texttt{availability.band} & string & Conservative qualitative availability classification. Values are \texttt{unknown}, \texttt{low}, \texttt{medium}, or \texttt{high}. \\
\texttt{availability.}\newline\texttt{quantity\_records} & array of objects & Numeric quantity, production, procurement, collection, or yield records extracted from sources. \\
\texttt{geography} & object & Granular geographic details beyond broad state-level data. \\
\texttt{geography.districts} & array of strings & Districts explicitly or reasonably supported by source text. \\
\texttt{geography.clusters} & array of strings & Named livelihood, processing, tribal, or Van Dhan clusters. \\
\texttt{relationship\_summary} & object & Inline summary of relationships for quick access by later modules. \\
\texttt{relationship\_summary.}\newline\texttt{related\_regions} & array of strings & States, districts, or clusters related to the material. \\
\texttt{relationship\_summary.}\newline\texttt{related\_products} & array of strings & Current and potential products related to the material. \\
\texttt{relationship\_summary.}\newline\texttt{related\_skills} & array of strings & Artisan or processing skill labels related to the material. \\
\texttt{relationship\_summary.}\newline\texttt{related\_material\_groups} & array of strings & Broad material group or category labels. \\
\texttt{confidence} & object & Confidence values for availability, geography, and relationship construction. \\
\texttt{evidence\_refs} & array of strings & Evidence IDs that support the deep enrichment block or relationship summary. \\
\texttt{last\_updated\_at} & string or null & UTC timestamp for the last additive enrichment update. \\
\end{longtable}
\endgroup

## Quantity Record Schema

Quantity records are intentionally conservative. They are stored only when a numeric statement is found in the retrieved evidence.

| Field | Type | Description | Example |
|---|---|---|---|
| `value` | number | Numeric quantity value. | `250000` |
| `unit` | string | Normalized unit. Common values include `tonnes`, `kg`, and `quintals`. | `tonnes` |
| `year` | integer or null | Year associated with the value, if available. | `2005` |
| `scope` | string or null | Short phrase describing the scope of the value. | `annual production` |
| `metric_type` | string or null | Type of quantity signal. Expected values include `collection`, `procurement`, `production`, and `yield`. | `production` |

## Deep Enrichment Coverage

| Deep Field | Coverage |
|---|---:|
| Records with `deep_enrichment` | 86 / 87 |
| Records with quantity records | 41 / 87 |
| Records with districts | 38 / 87 |
| Records with clusters | 24 / 87 |
| Records with relationship summary | 86 / 87 |

## Deep Status Distribution

| Status | Count |
|---|---:|
| `partial` | 65 |
| `not_started` | 21 |

## Availability Band Distribution

| Band | Count |
|---|---:|
| `medium` | 14 |
| `low` | 2 |
| `unknown` | 70 |

# Evidence Schema

Evidence records are stored in `data/deep_enrichment_evidence.json`. This file is a JSON object keyed by `evidence_id`. Each evidence record explains where a particular value came from and how strongly it is supported.

The evidence store is deliberately separate from the canonical item file. This keeps `enriched_mfp_data.json` readable while preserving detailed provenance in a dedicated reference file.

## Evidence Record Shape

```json
{
  "evidence_id": "evi_363051b04e7b5c30",
  "mfp_id": 1,
  "attribute_group": "availability",
  "attribute_name": "band",
  "value": "low",
  "source_url": "https://gef7folur.da.gov.in/wwwroot/Doc/ProDoc.pdf",
  "source_type": "official",
  "snippet": "Compound annual growth rates of area, production and yield...",
  "retrieved_at": "2026-06-21T08:38:25Z",
  "confidence": 0.3
}
```

## Evidence Field Dictionary

\begingroup
\small
\setlength{\tabcolsep}{4pt}
\renewcommand{\arraystretch}{1.2}
\begin{longtable}{p{0.26\textwidth} p{0.20\textwidth} p{0.46\textwidth}}
\textbf{Field} & \textbf{Type} & \textbf{Description} \\
\hline
\texttt{evidence\_id} & string & Deterministic evidence identifier generated from material ID, attribute, value, source URL, and snippet. \\
\texttt{mfp\_id} & integer & Material ID to which the evidence belongs. \\
\texttt{attribute\_group} & string & Broad group supported by the evidence. Examples: \texttt{availability}, \texttt{geography}, \texttt{relationship}. \\
\texttt{attribute\_name} & string & Specific attribute supported by the evidence. Examples: \texttt{band}, \texttt{quantity\_records}, \texttt{districts}, \texttt{state}, \texttt{skill}. \\
\texttt{value} & string, number, object, or array & The extracted or derived value supported by the evidence. \\
\texttt{source\_url} & string & URL or synthetic dataset reference from which the evidence was derived. \\
\texttt{source\_type} & string & Source category assigned by the system. \\
\texttt{snippet} & string & Short text excerpt or explanation supporting the value. \\
\texttt{retrieved\_at} & string & UTC timestamp indicating when the evidence record was created. \\
\texttt{confidence} & number & Confidence score between 0.0 and 1.0. \\
\end{longtable}
\endgroup

## Evidence Attribute Distribution

| Attribute Group | Count |
|---|---:|
| `relationship` | 1,206 |
| `availability` | 194 |
| `geography` | 102 |

| Attribute Name | Count |
|---|---:|
| `state` | 390 |
| `current_product` | 317 |
| `potential_product` | 236 |
| `skill` | 177 |
| `band` | 113 |
| `material_group` | 86 |
| `quantity_records` | 81 |
| `districts` | 71 |
| `clusters` | 31 |

# Source Classification and Locations

The dataset is built from multiple kinds of locations. Some are direct data files inside the project. Others are external web sources discovered through search and document retrieval.

## Internal Source Locations

| Location | Purpose |
|---|---|
| `MFP_List_87_Items_Split.csv` | Original seed list used to create material records. |
| `data/seed_mfp_list.json` | Cleaned seed representation used by the enrichment pipeline. |
| `data/enriched_mfp_data.json` | Canonical enriched dataset. |
| `data/enrichment_sources.json` | Base enrichment source tracking. |
| `data/deep_enrichment_evidence.json` | Evidence records for deep enrichment and relationships. |
| `data/material_relationships.json` | Graph-ready relationship edge list. |
| `data/deep_enrichment_runs/` | Run manifests, previews, and validation summaries. |
| `data/backups/` | Snapshots used for rollback and recovery. |

## External Source Types

The deep enrichment system classifies source URLs into trust categories. Source classification is implemented in `mfp_scraper/deep_models.py`.

| Source Type | Meaning | Typical Domain Hints |
|---|---|---|
| `official` | Government or official public-sector source. | `gov.in`, `nic.in` |
| `institutional` | Biodiversity, forestry, agricultural, or institutional source. | `gbif.org`, `powo.science.kew.org`, `indiabiodiversity.org`, `icfre.gov.in`, `icar.gov.in`, `nmpb.nic.in` |
| `research` | Research paper, journal, repository, or academic source. | `ncbi.nlm.nih.gov`, `researchgate.net`, `sciencedirect.com`, `springer.com`, `mdpi.com` |
| `supporting` | General web source used as secondary support. | Other web domains |
| `existing_dataset` | Synthetic source reference derived from existing canonical fields. | `dataset://enriched_mfp_data.json` |

## Evidence Source Distribution

| Source Type | Evidence Records |
|---|---:|
| `existing_dataset` | 1,206 |
| `official` | 175 |
| `research` | 74 |
| `supporting` | 47 |

The large number of `existing_dataset` records is expected. Many graph relationships, such as material-to-state or material-to-product edges, are derived from already validated canonical fields rather than from newly retrieved web documents.

# LLM Extraction Behavior

The LLM is used as a structured extraction assistant. It is not used to freely invent facts or decide the final dataset independently. The system retrieves source text first, creates a bounded source dossier, and then asks the LLM to extract specific fields in a strict JSON shape.

## Base LLM Extraction

Base enrichment uses the prompt defined in `mfp_scraper/llm_extractor.py`. The LLM receives the material name, category, existing scientific name, MSP, known states, and aggregated source text.

The base prompt asks the LLM to extract:

- scientific name
- description
- season
- shelf life
- states
- artisan types
- current products
- potential products
- confidence scores

The prompt includes constraints such as using specific Indian states instead of "All India," keeping shelf life as a short duration, and returning only valid JSON.

## Deep LLM Extraction

Deep enrichment uses the prompt defined in `mfp_scraper/deep_extractor.py`. This prompt is narrower than the base prompt. It extracts only availability and geography fields from the source dossier.

The deep prompt asks the LLM to extract:

- `availability.band`
- `availability.quantity_records`
- `geography.districts`
- `geography.clusters`
- supporting evidence entries
- confidence values for availability and geography

The LLM is explicitly instructed not to infer exact numeric quantities when the source does not state them. It is also instructed not to place whole states in the district list. This prevents broad geography from being incorrectly treated as granular location data.

## Where the LLM Explores

The LLM itself does not browse the web. Exploration is performed before the LLM call by the pipeline.

The system explores the web through targeted Serper search queries. For each material, the deep pipeline generates three query families:

| Query Family | Purpose | Example Pattern |
|---|---|---|
| `quantity` | Find production, collection, yield, or quantity claims. | `"Tamarind (with seeds)" India annual production OR collection OR yield tonnes` |
| `geography` | Find producing districts or clusters. | `"Tamarind (with seeds)" major producing districts India` |
| `relationships` | Find processing, value addition, and product links. | `"Tamarind (with seeds)" tribal value addition processing products` |

After search results are returned, the pipeline ranks sources by trust category, fetches the top documents, extracts text from HTML or PDF files, and passes the resulting source dossier to the LLM.

## LLM Output Handling

The LLM output is parsed as JSON. If the model returns markdown fences or extra formatting, the parser attempts to recover the JSON object. After parsing, the output is normalized:

- quantity records are deduplicated using value, unit, year, scope, and metric type
- districts and clusters are deduplicated case-insensitively
- invalid availability bands are reset to `unknown`
- unsupported source URLs are discarded during normalization
- missing or unreliable values are left empty rather than guessed

# Relationship Edge Schema

Relationship edges are stored in `data/material_relationships.json`. This file is a JSON array. Each object represents one directed graph edge from a material to another entity.

## Edge Record Shape

```json
{
  "edge_id": "edge_d7e284ed9506b1f9",
  "source_mfp_id": 1,
  "edge_type": "available_in",
  "target_type": "state",
  "target_value": "Tamil Nadu",
  "evidence_id": "evi_3be473ddd45f3573",
  "confidence": 1.0
}
```

## Edge Field Dictionary

| Field | Type | Description |
|---|---|---|
| `edge_id` | string | Deterministic edge identifier generated from source material, edge type, target type, target value, and evidence ID. |
| `source_mfp_id` | integer | MFP material ID from which the relationship originates. |
| `edge_type` | string | Type of relationship being represented. |
| `target_type` | string | Type of target entity. Examples include `state`, `district`, `skill`, `current_product`, and `potential_product`. |
| `target_value` | string | Human-readable target entity value. |
| `evidence_id` | string | Evidence record supporting the relationship. |
| `confidence` | number | Confidence score between 0.0 and 1.0. |

## Edge Type Dictionary

| Edge Type | Target Types | Meaning |
|---|---|---|
| `available_in` | `state`, `district` | Indicates that a material is available, collected, produced, or associated with a region. |
| `linked_to` | `cluster` | Links a material to a cluster or institutional grouping. |
| `processed_by` | `skill` | Links a material to artisan, collector, or processor skill types. |
| `used_for_product` | `current_product` | Links a material to an existing product. |
| `could_enable_product` | `potential_product` | Links a material to a possible value-added product. |
| `belongs_to_group` | `material_group` | Links a material to its category or broader material class. |

## Relationship Edge Distribution

| Edge Type | Count |
|---|---:|
| `available_in` | 426 |
| `processed_by` | 177 |
| `used_for_product` | 317 |
| `could_enable_product` | 236 |
| `belongs_to_group` | 86 |
| `linked_to` | 17 |

## Target Type Distribution

| Target Type | Count |
|---|---:|
| `state` | 390 |
| `district` | 36 |
| `skill` | 177 |
| `current_product` | 317 |
| `potential_product` | 236 |
| `material_group` | 86 |
| `cluster` | 17 |

# How Relationships Are Built

The relationship graph is built primarily in `mfp_scraper/deep_pipeline.py`. The system uses both existing canonical fields and new deep enrichment fields.

Relationships are created deterministically. This means the graph is not left to the LLM to invent. The LLM helps identify availability and geography evidence, but most relationship edges are constructed by explicit rules.

The relationship construction process is as follows.

1. For every state in `states`, create an `available_in` edge to a `state` target.
2. For every district found in deep geography evidence, create an `available_in` edge to a `district` target.
3. For every cluster found in deep geography evidence, create a `linked_to` edge to a `cluster` target.
4. For every artisan type in `artisan_types`, create a `processed_by` edge to a `skill` target.
5. For every current product in `current_products`, create a `used_for_product` edge to a `current_product` target.
6. For every potential product in `potential_products`, create a `could_enable_product` edge to a `potential_product` target.
7. For the material category, create a `belongs_to_group` edge to a `material_group` target.

Each generated edge receives an `edge_id` and an `evidence_id`. When the edge comes from an existing canonical field, the evidence source is synthetic and uses the format `dataset://enriched_mfp_data.json#mfp_id=<id>&field=<field_name>`. When the edge comes from newly retrieved geography evidence, the evidence source points to the external document URL.

# Confidence Scoring Reference

Confidence scores are numeric values between 0.0 and 1.0. They should be interpreted as system confidence in the extracted or derived value, not as statistical probability.

| Range | Interpretation |
|---|---|
| `0.0` | No evidence or not populated. |
| `0.1 - 0.4` | Weak or limited support. Use for review only. |
| `0.5 - 0.7` | Moderate support from source text or extracted evidence. |
| `0.8 - 0.9` | Strong support from explicit source material. |
| `1.0` | Directly derived from existing canonical dataset fields or otherwise treated as deterministic. |

In the relationship graph, many edges have confidence `1.0` because they are deterministic transformations of existing canonical fields. This does not mean the real-world fact can never be wrong. It means the relationship edge accurately represents what is already present in the canonical dataset.

# Validation and Integrity Rules

Validation is performed at two levels: base validation and deep validation.

Base validation checks the canonical enrichment fields. It reports completeness, missing fields, low-confidence fields, and potential issues such as excessive state lists or overlap between current and potential products.

Deep validation checks the relationship between the canonical dataset and the sidecar files. It verifies that evidence references exist, relationship edges point to valid material IDs, and edge evidence IDs are present in the evidence store.

The main integrity rules are:

- `mfp_id` must remain stable across all files
- every `deep_enrichment.evidence_refs` entry should exist in `deep_enrichment_evidence.json`
- every relationship edge should point to an existing material ID
- every relationship edge should have a valid `evidence_id`
- existing top-level canonical fields should not be changed by deep enrichment
- deep enrichment should remain additive and reversible

# Example: Tamarind Record

The following example demonstrates how one material record is represented across the canonical dataset, evidence store, and relationship graph.

## Canonical Material Context

| Field | Value |
|---|---|
| `mfp_id` | `1` |
| `name` | `Tamarind (with seeds)` |
| `scientific_name` | `Tamarindus indica` |
| `category` | `Forest Produce` |
| `states` | `Tamil Nadu`, `Madhya Pradesh`, `Andhra Pradesh`, `Maharashtra`, `Karnataka` |
| `season` | `March-April` |
| `shelf_life` | `9-12 months` |

## Deep Enrichment Summary

| Field | Value |
|---|---|
| `status` | `partial` |
| `availability.band` | `medium` |
| `availability.quantity_records` | 3 records |
| `geography.districts` | 0 records |
| `geography.clusters` | 0 records |
| `confidence.availability` | `0.7` |
| `confidence.geography` | `0.0` |
| `confidence.relationships` | `1.0` |

One quantity record for Tamarind is shown below.

```json
{
  "value": 250000,
  "unit": "tonnes",
  "year": null,
  "scope": "annual production",
  "metric_type": "production"
}
```

## Evidence Example

```json
{
  "evidence_id": "evi_adc55b0a0de69420",
  "mfp_id": 1,
  "attribute_group": "availability",
  "attribute_name": "quantity_records",
  "value": "250000 tonnes",
  "source_url": "https://journalcra.com/sites/default/files/issue-pdf/49267.pdf",
  "source_type": "supporting",
  "snippet": "Extensive tamarind orchards in India produce 250,000 tonnes...",
  "retrieved_at": "2026-06-21T08:38:25Z",
  "confidence": 0.8
}
```

## Relationship Edge Example

```json
{
  "edge_id": "edge_d7e284ed9506b1f9",
  "source_mfp_id": 1,
  "edge_type": "available_in",
  "target_type": "state",
  "target_value": "Tamil Nadu",
  "evidence_id": "evi_3be473ddd45f3573",
  "confidence": 1.0
}
```

# Schema Usage by Future Modules

The Data Dictionary is not only a reference for the current module. It also defines how later MAERII modules should use the knowledge base.

| Future Module | Relevant Fields |
|---|---|
| Market Demand Intelligence | `current_products`, `potential_products`, `material_relationships.json` |
| Product Recommendation AI | `states`, `artisan_types`, `availability`, `geography`, product edges |
| Product Design Enhancement AI | `current_products`, `potential_products`, `artisan_types`, material group |
| Quality Grading | `category`, `description`, `shelf_life`, source evidence |
| Pricing Engine | `msp`, `unit`, `availability.band`, quantity records, product relationships |

The canonical item file should be used when a module needs a material profile. The relationship sidecar should be used when a module needs connected reasoning, such as finding all materials available in a state or all products linked to a material group. The evidence file should be used when a module or human reviewer needs to verify where a value came from.



# Conclusion

The Raw Material Knowledge Engine dataset is structured around a clear separation of concerns. The canonical dataset stores material records, the evidence store preserves provenance, and the relationship file represents the knowledge graph layer. This structure allows the project to remain readable, auditable, and extensible.

The LLM's role is controlled and narrow. It extracts structured values from retrieved source text, while deterministic code handles normalization, deduplication, evidence linking, and relationship construction. This design gives MAERII a dataset that is not merely enriched, but explainable.

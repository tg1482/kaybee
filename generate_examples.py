"""Generate 4 example graph HTML files for exploration."""

from kaybee.core import KnowledgeGraph
from kaybee.viz import visualize


def graph_1_cognitive_science():
    """Small cognitive science knowledge base."""
    kg = KnowledgeGraph()
    kg.add_type("concept")
    kg.add_type("person")
    kg.add_type("paper")

    kg.write("spreading-activation", """---
type: concept
description: How activation propagates through a network
tags: [graph, cognition, search]
---
Spreading activation is a method for searching associative networks.
It follows [[agent-traversal]] paths and uses [[semantic-similarity]].
First described by [[collins]].""")

    kg.write("agent-traversal", """---
type: concept
description: How agents navigate graph structures
tags: [graph, agents, ai]
---
Traversal strategies let agents explore graphs efficiently.
Often combined with [[spreading-activation]] for discovery.
See also [[breadth-first-search]] and [[depth-first-search]].""")

    kg.write("semantic-similarity", """---
type: concept
description: Measuring meaning overlap between items
tags: [nlp, embeddings, cognition]
---
Semantic similarity quantifies how close two meanings are.
Used in [[spreading-activation]] and [[word2vec]].""")

    kg.write("breadth-first-search", """---
type: concept
description: Level-by-level graph traversal
tags: [graph, algorithms]
---
BFS explores neighbors before going deeper. Core to [[agent-traversal]].""")

    kg.write("depth-first-search", """---
type: concept
description: Explore as far as possible before backtracking
tags: [graph, algorithms]
---
DFS goes deep first. Alternative to [[breadth-first-search]].
Used in [[agent-traversal]].""")

    kg.write("word2vec", """---
type: concept
description: Neural word embeddings
tags: [nlp, embeddings, ml]
---
Word2Vec learns vector representations of words.
Enables [[semantic-similarity]] computation. Created by [[mikolov]].""")

    kg.write("attention-mechanism", """---
type: concept
description: Selective focus in neural networks
tags: [ml, transformers, cognition]
---
Attention lets models focus on relevant parts of input.
Related to [[spreading-activation]] in biological cognition.
Key component of [[transformer]].""")

    kg.write("transformer", """---
type: concept
description: Self-attention based architecture
tags: [ml, transformers, ai]
---
The Transformer architecture relies on [[attention-mechanism]].
Introduced by [[vaswani]].""")

    kg.write("collins", """---
type: person
role: cognitive scientist
tags: [cognition]
---
Allan Collins developed [[spreading-activation]] theory
with Ross Quillian.""")

    kg.write("mikolov", """---
type: person
role: researcher
tags: [nlp, ml]
---
Tomas Mikolov created [[word2vec]] at Google.""")

    kg.write("vaswani", """---
type: person
role: researcher
tags: [ml, transformers]
---
Ashish Vaswani co-authored the [[transformer]] paper "Attention Is All You Need".""")

    kg.write("turing", """---
type: person
role: pioneer
tags: [ai, computation]
---
Alan Turing pioneered computation theory and early ideas about [[agent-traversal]].""")

    kg.write("attention-is-all-you-need", """---
type: paper
year: 2017
tags: [transformers, ml]
---
Landmark paper introducing the [[transformer]] architecture.
By [[vaswani]] et al.""")

    kg.touch("readme", "Welcome to the cognitive science knowledge graph.")
    visualize(kg, path="examples/cognitive_science.html")
    print(f"  cognitive_science.html: {len(kg.ls('*'))} nodes, {len(kg.types())} types")


def graph_2_software_architecture():
    """Software architecture concepts."""
    kg = KnowledgeGraph()
    kg.add_type("pattern")
    kg.add_type("principle")
    kg.add_type("technology")

    kg.write("microservices", """---
type: pattern
description: Decompose into small independent services
tags: [architecture, distributed, scalability]
---
Microservices break a system into independently deployable services.
Often uses [[api-gateway]] and [[service-mesh]].
Contrast with [[monolith]].""")

    kg.write("monolith", """---
type: pattern
description: Single deployable unit
tags: [architecture, simplicity]
---
A monolithic architecture is a single deployable unit.
Simpler than [[microservices]] but harder to scale.
Can apply [[solid]] principles internally.""")

    kg.write("api-gateway", """---
type: pattern
description: Single entry point for API calls
tags: [architecture, distributed, api]
---
Routes requests to [[microservices]]. Handles auth, rate limiting.
Often paired with [[load-balancer]].""")

    kg.write("service-mesh", """---
type: technology
description: Infrastructure layer for service-to-service communication
tags: [distributed, networking, observability]
---
Manages communication between [[microservices]].
Provides [[circuit-breaker]] and observability.""")

    kg.write("load-balancer", """---
type: technology
description: Distributes traffic across servers
tags: [distributed, scalability, networking]
---
Distributes incoming requests. Works with [[api-gateway]].
Enables [[horizontal-scaling]].""")

    kg.write("circuit-breaker", """---
type: pattern
description: Prevent cascade failures
tags: [distributed, resilience]
---
Stops calling a failing service. Used in [[service-mesh]].
Implements [[fault-tolerance]].""")

    kg.write("cqrs", """---
type: pattern
description: Separate read and write models
tags: [architecture, data, scalability]
---
Command Query Responsibility Segregation.
Often paired with [[event-sourcing]]. Enables [[horizontal-scaling]].""")

    kg.write("event-sourcing", """---
type: pattern
description: Store events instead of current state
tags: [data, architecture, audit]
---
Every state change is an event. Works well with [[cqrs]].
Enables audit trails and [[saga-pattern]].""")

    kg.write("saga-pattern", """---
type: pattern
description: Manage distributed transactions
tags: [distributed, data, resilience]
---
Coordinates transactions across [[microservices]].
Uses compensation for rollback. Related to [[event-sourcing]].""")

    kg.write("solid", """---
type: principle
description: Five principles of OO design
tags: [design, oop]
---
Single responsibility, Open-closed, Liskov substitution,
Interface segregation, Dependency inversion.
Apply within [[monolith]] or [[microservices]].""")

    kg.write("fault-tolerance", """---
type: principle
description: System continues operating despite failures
tags: [resilience, distributed]
---
Achieved via [[circuit-breaker]], retries, and redundancy.
Critical for [[microservices]] architectures.""")

    kg.write("horizontal-scaling", """---
type: principle
description: Scale by adding more machines
tags: [scalability, distributed]
---
Add more instances behind a [[load-balancer]].
Enabled by stateless design and [[cqrs]].""")

    kg.write("docker", """---
type: technology
description: Container runtime
tags: [devops, containers]
---
Packages apps in containers. Foundation for [[kubernetes]].
Simplifies [[microservices]] deployment.""")

    kg.write("kubernetes", """---
type: technology
description: Container orchestration
tags: [devops, containers, distributed]
---
Orchestrates [[docker]] containers at scale.
Manages [[microservices]] lifecycle. Includes [[load-balancer]].""")

    visualize(kg, path="examples/software_architecture.html")
    print(f"  software_architecture.html: {len(kg.ls('*'))} nodes, {len(kg.types())} types")


def graph_3_biology():
    """Cell biology knowledge base."""
    kg = KnowledgeGraph()
    kg.add_type("organelle")
    kg.add_type("process")
    kg.add_type("molecule")

    kg.write("mitochondria", """---
type: organelle
description: Powerhouse of the cell
tags: [energy, metabolism]
---
Mitochondria generate ATP via [[oxidative-phosphorylation]].
Has its own DNA. Involved in [[apoptosis]].""")

    kg.write("ribosome", """---
type: organelle
description: Protein synthesis machinery
tags: [protein, rna]
---
Ribosomes translate [[mrna]] into [[protein]].
Can be free or bound to [[endoplasmic-reticulum]].""")

    kg.write("endoplasmic-reticulum", """---
type: organelle
description: Membrane system for protein processing
tags: [protein, membrane]
---
Rough ER has [[ribosome]]s. Processes [[protein]]s.
Sends to [[golgi-apparatus]].""")

    kg.write("golgi-apparatus", """---
type: organelle
description: Protein packaging and sorting
tags: [protein, membrane, transport]
---
Modifies proteins from [[endoplasmic-reticulum]].
Packages into vesicles for [[exocytosis]].""")

    kg.write("nucleus", """---
type: organelle
description: Contains genetic material
tags: [dna, gene-expression]
---
Houses [[dna]]. Site of [[transcription]].
Controls [[gene-expression]].""")

    kg.write("transcription", """---
type: process
description: DNA to mRNA
tags: [gene-expression, rna]
---
Converts [[dna]] to [[mrna]] in the [[nucleus]].
First step of [[gene-expression]].""")

    kg.write("translation", """---
type: process
description: mRNA to protein
tags: [protein, rna]
---
[[ribosome]]s read [[mrna]] to build [[protein]].
Second step of [[gene-expression]].""")

    kg.write("oxidative-phosphorylation", """---
type: process
description: ATP production in mitochondria
tags: [energy, metabolism]
---
Produces ATP in [[mitochondria]]. Uses electron transport chain.
Requires [[atp-synthase]].""")

    kg.write("apoptosis", """---
type: process
description: Programmed cell death
tags: [cell-death, regulation]
---
Controlled cell death. [[mitochondria]] release cytochrome c.
Triggered by [[dna]] damage.""")

    kg.write("gene-expression", """---
type: process
description: DNA to functional product
tags: [gene-expression, regulation]
---
Two main steps: [[transcription]] and [[translation]].
Regulated at multiple levels. Occurs in [[nucleus]] and cytoplasm.""")

    kg.write("exocytosis", """---
type: process
description: Secretion from cell
tags: [transport, membrane]
---
Vesicles from [[golgi-apparatus]] fuse with cell membrane.
Releases [[protein]]s outside.""")

    kg.write("dna", """---
type: molecule
description: Genetic blueprint
tags: [dna, gene-expression]
---
Double helix in [[nucleus]]. Template for [[transcription]].
Damage can trigger [[apoptosis]].""")

    kg.write("mrna", """---
type: molecule
description: Messenger RNA
tags: [rna, gene-expression]
---
Product of [[transcription]]. Read by [[ribosome]] during [[translation]].""")

    kg.write("protein", """---
type: molecule
description: Functional molecular machines
tags: [protein]
---
Built by [[translation]]. Processed in [[endoplasmic-reticulum]].
Sorted by [[golgi-apparatus]].""")

    kg.write("atp-synthase", """---
type: molecule
description: Enzyme that makes ATP
tags: [energy, metabolism, protein]
---
Rotary enzyme in [[mitochondria]]. Drives [[oxidative-phosphorylation]].
Is itself a [[protein]].""")

    visualize(kg, path="examples/biology.html")
    print(f"  biology.html: {len(kg.ls('*'))} nodes, {len(kg.types())} types")


def graph_4_music_theory():
    """Music theory concepts."""
    kg = KnowledgeGraph()
    kg.add_type("concept")
    kg.add_type("scale")
    kg.add_type("genre")
    kg.add_type("technique")

    kg.write("harmony", """---
type: concept
description: Simultaneous combination of tones
tags: [theory, composition]
---
Harmony is the vertical aspect of music. Based on [[chord]]s.
Contrast with [[melody]] (horizontal). Governed by [[voice-leading]].""")

    kg.write("melody", """---
type: concept
description: Sequence of single tones
tags: [theory, composition]
---
Melody is the horizontal line. Interacts with [[harmony]].
Uses [[scale]]s and [[interval]]s.""")

    kg.write("rhythm", """---
type: concept
description: Pattern of durations and accents
tags: [theory, performance]
---
Rhythm organizes time. [[syncopation]] creates tension.
Foundation of [[jazz]] and [[funk]].""")

    kg.write("chord", """---
type: concept
description: Three or more notes sounded together
tags: [theory, harmony]
---
Building block of [[harmony]]. Built from [[interval]]s.
[[chord-progression]]s create movement.""")

    kg.write("interval", """---
type: concept
description: Distance between two pitches
tags: [theory]
---
Intervals are the atoms of [[melody]] and [[chord]]s.
Measured in semitones.""")

    kg.write("chord-progression", """---
type: concept
description: Sequence of chords
tags: [theory, harmony, composition]
---
Chord progressions drive [[harmony]]. Governed by [[voice-leading]].
ii-V-I is fundamental to [[jazz]].""")

    kg.write("voice-leading", """---
type: technique
description: Smooth movement between chords
tags: [theory, harmony, composition]
---
Minimizes motion between [[chord]] tones.
Essential for [[counterpoint]] and [[chord-progression]]s.""")

    kg.write("counterpoint", """---
type: technique
description: Independent melodic lines
tags: [theory, composition, classical]
---
Multiple [[melody]] lines with [[harmony]].
Uses [[voice-leading]] rules. Perfected in [[classical]].""")

    kg.write("syncopation", """---
type: technique
description: Accents on weak beats
tags: [rhythm, performance]
---
Shifts accents off the beat. Defines [[jazz]] and [[funk]] [[rhythm]].""")

    kg.write("improvisation", """---
type: technique
description: Spontaneous musical creation
tags: [performance, creativity]
---
Creating music in real-time. Central to [[jazz]].
Uses [[scale]]s, [[chord-progression]]s, and [[rhythm]].""")

    kg.write("major-scale", """---
type: scale
description: W-W-H-W-W-W-H pattern
tags: [theory, scales]
---
The major scale. Basis of Western [[harmony]].
Modes include [[dorian]] and [[mixolydian]].""")

    kg.write("minor-scale", """---
type: scale
description: Natural minor pattern
tags: [theory, scales]
---
Darker than [[major-scale]]. Used heavily in [[blues]] and [[jazz]].""")

    kg.write("pentatonic", """---
type: scale
description: Five-note scale
tags: [theory, scales, improvisation]
---
Subset of [[major-scale]]/[[minor-scale]]. Universal across cultures.
Great for [[improvisation]].""")

    kg.write("blues-scale", """---
type: scale
description: Minor pentatonic plus blue note
tags: [theory, scales, blues]
---
Adds a flat 5th to [[pentatonic]]. Defines [[blues]] sound.
Used in [[jazz]] and [[rock]].""")

    kg.write("jazz", """---
type: genre
description: Improvisation-driven American music
tags: [genre, improvisation]
---
Built on [[improvisation]], [[chord-progression]]s, and [[syncopation]].
Uses [[blues-scale]], [[dorian]], [[mixolydian]].""")

    kg.write("blues", """---
type: genre
description: African-American roots music
tags: [genre, roots]
---
12-bar [[chord-progression]]. [[blues-scale]] and [[pentatonic]].
Foundation for [[jazz]] and [[rock]].""")

    kg.write("classical", """---
type: genre
description: Western art music tradition
tags: [genre, composition]
---
Emphasizes [[counterpoint]], [[harmony]], and form.
Strict [[voice-leading]] rules.""")

    kg.write("rock", """---
type: genre
description: Electric guitar driven popular music
tags: [genre, popular]
---
Evolved from [[blues]]. Power chords ([[chord]]s).
Strong [[rhythm]]. Uses [[pentatonic]] and [[blues-scale]].""")

    kg.write("funk", """---
type: genre
description: Groove-driven rhythmic music
tags: [genre, rhythm]
---
All about [[rhythm]] and [[syncopation]].
Strong bass lines and [[chord]] stabs.""")

    kg.write("dorian", """---
type: scale
description: Minor mode with raised 6th
tags: [theory, scales, jazz]
---
Mode of [[major-scale]]. Popular in [[jazz]] [[improvisation]].
Darker than major, brighter than [[minor-scale]].""")

    kg.write("mixolydian", """---
type: scale
description: Major mode with flat 7th
tags: [theory, scales, jazz]
---
Mode of [[major-scale]]. Dominant sound in [[jazz]] and [[blues]].
Used over dominant [[chord]]s.""")

    visualize(kg, path="examples/music_theory.html")
    print(f"  music_theory.html: {len(kg.ls('*'))} nodes, {len(kg.types())} types")


if __name__ == "__main__":
    import os
    os.makedirs("examples", exist_ok=True)
    print("Generating example graphs...")
    graph_1_cognitive_science()
    graph_2_software_architecture()
    graph_3_biology()
    graph_4_music_theory()
    print("Done! Open the HTML files in a browser.")

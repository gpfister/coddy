"""Pydantic v2 schemas for GraphRAG data models and cache persistence."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphNode(BaseModel):
    """Represents a node in the FalkorDB graph."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique node identifier")
    labels: list[str] = Field(default_factory=list, description="List of labels applied to this node")
    properties: dict[str, Any] = Field(default_factory=dict, description="Arbitrary scalar properties of the node")


class GraphEdge(BaseModel):
    """Represents a directed edge in the FalkorDB graph."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Source node identifier")
    target: str = Field(description="Target node identifier")
    type: str = Field(description="Relationship type (e.g. CALLS, DEFINES, IMPORTS)")
    properties: dict[str, Any] = Field(default_factory=dict, description="Arbitrary scalar properties of the edge")


class GraphExport(BaseModel):
    """Schema for graph.json cache persistence."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="1.0", description="Schema version of the graph export")
    commit_sha: str = Field(description="Git commit SHA for which this graph was ingested")
    nodes: list[GraphNode] = Field(default_factory=list, description="All nodes in the graph")
    edges: list[GraphEdge] = Field(default_factory=list, description="All directed edges in the graph")


class SparseVector(BaseModel):
    """Represents a sparse vector with indices and values for BM25/BM42."""

    model_config = ConfigDict(extra="forbid")

    indices: list[int] = Field(default_factory=list, description="Indices of non-zero sparse dimensions")
    values: list[float] = Field(default_factory=list, description="Values for non-zero sparse dimensions")


class VectorItem(BaseModel):
    """Represents a single vectorized item in Qdrant with sparse vectors."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique object UUID or identifier")
    properties: dict[str, Any] = Field(default_factory=dict, description="Properties of the vector object")
    vector: list[float] = Field(default_factory=list, description="Dense vector embedding values (optional)")
    sparse_vectors: dict[str, SparseVector] = Field(
        default_factory=dict,
        description="Map of sparse vector names ('bm25', 'bm42') to sparse vector data",
    )


class VectorsExport(BaseModel):
    """Schema for vectors.json cache persistence."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="1.0", description="Schema version of the vectors export")
    commit_sha: str = Field(description="Git commit SHA for which vectors were generated")
    collections: dict[str, list[VectorItem]] = Field(
        default_factory=dict,
        description="Map of collection name (e.g. DocChunk, Fact) to vectorized items",
    )


class IngestionStats(BaseModel):
    """Execution statistics returned by GraphRAG ingestion."""

    model_config = ConfigDict(extra="forbid")

    nodes: int = Field(default=0, description="Total graph nodes created")
    edges: int = Field(default=0, description="Total graph edges created")
    chunks: int = Field(default=0, description="Total doc chunks ingested")
    facts: int = Field(default=0, description="Total facts extracted and vectorized")

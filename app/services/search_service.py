"""
Multimodal Search Service for unified search across all data sources.

Supports:
- Full-text search (transcriptions, descriptions, metadata)
- Face search (similarity matching)
- Keyword search
- Combined ranking using Reciprocal Rank Fusion (RRF)
"""

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.search import (
    MatchInfo,
    MultimodalSearchRequest,
    MultimodalSearchResponse,
    MultimodalSearchResult,
    SearchSuggestion,
)

logger = logging.getLogger(__name__)


class SearchService:
    """Service for multimodal search across all data sources."""

    def __init__(self):
        self.rrf_k = 60  # RRF constant (typically 60)

    async def search(
        self,
        db: AsyncSession,
        request: MultimodalSearchRequest,
        tenant_id: UUID,
    ) -> MultimodalSearchResponse:
        """
        Execute a multimodal search across all enabled sources.

        Args:
            db: Database session
            request: Search request with query and options
            tenant_id: Tenant UUID for isolation

        Returns:
            MultimodalSearchResponse with combined results
        """
        start_time = time.time()

        results_by_asset: dict[UUID, dict[str, Any]] = {}
        modes_used: list[str] = []

        # Search transcriptions
        if request.modes.transcription:
            transcription_results = await self._search_transcriptions(
                db, request.query, tenant_id, request.filters
            )
            self._merge_results(results_by_asset, transcription_results, "transcription")
            if transcription_results:
                modes_used.append("transcription")

        # Search scene descriptions
        if request.modes.scene:
            scene_results = await self._search_scenes(
                db, request.query, tenant_id, request.filters
            )
            self._merge_results(results_by_asset, scene_results, "scene")
            if scene_results:
                modes_used.append("scene")

        # Search keywords
        if request.modes.keywords:
            keyword_results = await self._search_keywords(
                db, request.query, tenant_id, request.filters
            )
            self._merge_results(results_by_asset, keyword_results, "keyword")
            if keyword_results:
                modes_used.append("keyword")

        # Search metadata (title, description)
        if request.modes.metadata:
            metadata_results = await self._search_metadata(
                db, request.query, tenant_id, request.filters
            )
            self._merge_results(results_by_asset, metadata_results, "metadata")
            if metadata_results:
                modes_used.append("metadata")

        # Search faces (if face image provided)
        if request.modes.face and request.face_image:
            face_results = await self._search_faces(
                db, request.face_image, tenant_id, request.filters
            )
            self._merge_results(results_by_asset, face_results, "face")
            if face_results:
                modes_used.append("face")

        # Calculate combined scores using RRF
        for asset_id, data in results_by_asset.items():
            data["combined_score"] = self._calculate_rrf_score(data["matches"])

        # Sort by combined score
        sorted_results = sorted(
            results_by_asset.values(),
            key=lambda x: x["combined_score"],
            reverse=True,
        )

        # Apply pagination
        total = len(sorted_results)
        paginated = sorted_results[request.offset : request.offset + request.limit]

        # Format results
        formatted_results = [
            MultimodalSearchResult(
                asset_id=r["asset_id"],
                title=r.get("title"),
                description=r.get("description"),
                asset_type=r.get("asset_type", "unknown"),
                status=r.get("status", "unknown"),
                thumbnail_url=r.get("thumbnail_url"),
                duration_ms=r.get("duration_ms"),
                matches=r["matches"],
                combined_score=r["combined_score"],
                created_at=r.get("created_at"),
            )
            for r in paginated
        ]

        search_time_ms = int((time.time() - start_time) * 1000)

        return MultimodalSearchResponse(
            query=request.query,
            total=total,
            limit=request.limit,
            offset=request.offset,
            search_time_ms=search_time_ms,
            results=formatted_results,
            modes_used=modes_used,
        )

    async def _search_transcriptions(
        self,
        db: AsyncSession,
        query: str,
        tenant_id: UUID,
        filters: Any,
    ) -> list[dict[str, Any]]:
        """Search in transcription full text."""
        sql = """
            SELECT
                t.asset_id,
                t.id as transcription_id,
                a.title,
                a.description,
                a.asset_type,
                a.status,
                a.duration_ms,
                a.created_at,
                ts_rank(t.search_vector, plainto_tsquery('portuguese', :query)) as rank,
                ts_headline('portuguese', t.full_text, plainto_tsquery('portuguese', :query),
                    'MaxWords=30, MinWords=15, StartSel=<mark>, StopSel=</mark>') as headline
            FROM asset_transcriptions t
            JOIN assets a ON a.id = t.asset_id
            WHERE t.tenant_id = :tenant_id
            AND t.search_vector @@ plainto_tsquery('portuguese', :query)
        """

        # Add filters
        params = {"tenant_id": tenant_id, "query": query}
        sql = self._add_filters(sql, filters, params)

        sql += " ORDER BY rank DESC LIMIT 100"

        result = await db.execute(text(sql), params)
        rows = result.fetchall()

        return [
            {
                "asset_id": row.asset_id,
                "title": row.title,
                "description": row.description,
                "asset_type": row.asset_type,
                "status": row.status,
                "duration_ms": row.duration_ms,
                "created_at": row.created_at,
                "match": MatchInfo(
                    type="transcription",
                    text=row.headline,
                    score=float(row.rank),
                ),
                "rank": float(row.rank),
            }
            for row in rows
        ]

    async def _search_scenes(
        self,
        db: AsyncSession,
        query: str,
        tenant_id: UUID,
        filters: Any,
    ) -> list[dict[str, Any]]:
        """Search in scene descriptions."""
        sql = """
            SELECT
                s.asset_id,
                a.title,
                a.asset_type,
                a.status,
                a.duration_ms,
                a.created_at,
                s.timecode_start_ms,
                s.description,
                ts_rank(s.search_vector, plainto_tsquery('portuguese', :query)) as rank
            FROM asset_scene_descriptions s
            JOIN assets a ON a.id = s.asset_id
            WHERE s.tenant_id = :tenant_id
            AND s.search_vector @@ plainto_tsquery('portuguese', :query)
        """

        params = {"tenant_id": tenant_id, "query": query}
        sql = self._add_filters(sql, filters, params)
        sql += " ORDER BY rank DESC LIMIT 100"

        result = await db.execute(text(sql), params)
        rows = result.fetchall()

        return [
            {
                "asset_id": row.asset_id,
                "title": row.title,
                "asset_type": row.asset_type,
                "status": row.status,
                "duration_ms": row.duration_ms,
                "created_at": row.created_at,
                "match": MatchInfo(
                    type="scene",
                    timecode_ms=row.timecode_start_ms,
                    description=row.description[:200],
                    score=float(row.rank),
                ),
                "rank": float(row.rank),
            }
            for row in rows
        ]

    async def _search_keywords(
        self,
        db: AsyncSession,
        query: str,
        tenant_id: UUID,
        filters: Any,
    ) -> list[dict[str, Any]]:
        """Search in keywords (manual and AI-extracted)."""
        # Search in asset_keywords
        sql1 = """
            SELECT
                k.asset_id,
                a.title,
                a.asset_type,
                a.status,
                a.duration_ms,
                a.created_at,
                k.keyword,
                k.start_ms as timecode_ms,
                1.0 as rank
            FROM asset_keywords k
            JOIN assets a ON a.id = k.asset_id
            WHERE k.tenant_id = :tenant_id
            AND k.keyword_normalized ILIKE :query_pattern
        """

        # Search in ai_extracted_keywords
        sql2 = """
            SELECT
                k.asset_id,
                a.title,
                a.asset_type,
                a.status,
                a.duration_ms,
                a.created_at,
                k.keyword,
                k.start_ms as timecode_ms,
                k.confidence as rank
            FROM ai_extracted_keywords k
            JOIN assets a ON a.id = k.asset_id
            WHERE k.tenant_id = :tenant_id
            AND k.keyword_normalized ILIKE :query_pattern
        """

        params = {
            "tenant_id": tenant_id,
            "query_pattern": f"%{query.lower()}%",
        }

        results = []

        for sql in [sql1, sql2]:
            sql = self._add_filters(sql, filters, params)
            sql += " LIMIT 50"

            result = await db.execute(text(sql), params)
            rows = result.fetchall()

            for row in rows:
                results.append({
                    "asset_id": row.asset_id,
                    "title": row.title,
                    "asset_type": row.asset_type,
                    "status": row.status,
                    "duration_ms": row.duration_ms,
                    "created_at": row.created_at,
                    "match": MatchInfo(
                        type="keyword",
                        keyword=row.keyword,
                        timecode_ms=row.timecode_ms,
                        score=float(row.rank) if row.rank else 0.5,
                    ),
                    "rank": float(row.rank) if row.rank else 0.5,
                })

        return results

    async def _search_metadata(
        self,
        db: AsyncSession,
        query: str,
        tenant_id: UUID,
        filters: Any,
    ) -> list[dict[str, Any]]:
        """Search in asset title and description."""
        sql = """
            SELECT
                a.id as asset_id,
                a.title,
                a.description,
                a.asset_type,
                a.status,
                a.duration_ms,
                a.created_at,
                ts_rank(a.search_vector, plainto_tsquery('portuguese', :query)) as rank,
                ts_headline('portuguese', a.title, plainto_tsquery('portuguese', :query),
                    'MaxWords=20, StartSel=<mark>, StopSel=</mark>') as headline
            FROM assets a
            WHERE a.tenant_id = :tenant_id
            AND a.search_vector @@ plainto_tsquery('portuguese', :query)
        """

        params = {"tenant_id": tenant_id, "query": query}
        sql = self._add_filters(sql, filters, params)
        sql += " ORDER BY rank DESC LIMIT 100"

        result = await db.execute(text(sql), params)
        rows = result.fetchall()

        return [
            {
                "asset_id": row.asset_id,
                "title": row.title,
                "description": row.description,
                "asset_type": row.asset_type,
                "status": row.status,
                "duration_ms": row.duration_ms,
                "created_at": row.created_at,
                "match": MatchInfo(
                    type="metadata",
                    text=row.headline,
                    score=float(row.rank),
                ),
                "rank": float(row.rank),
            }
            for row in rows
        ]

    async def _search_faces(
        self,
        db: AsyncSession,
        face_image: str,
        tenant_id: UUID,
        filters: Any,
    ) -> list[dict[str, Any]]:
        """Search for similar faces using image embedding."""
        from app.services.face_service import face_service

        try:
            # Get embedding from uploaded image
            import asyncio
            embedding = await face_service.get_embedding_from_image(face_image)

            sql = """
                SELECT
                    f.asset_id,
                    a.title,
                    a.asset_type,
                    a.status,
                    a.duration_ms,
                    a.created_at,
                    f.timecode_ms,
                    f.person_id,
                    p.name as person_name,
                    1 - (f.face_embedding <=> :embedding::vector) as similarity
                FROM asset_faces f
                JOIN assets a ON a.id = f.asset_id
                LEFT JOIN persons p ON p.id = f.person_id
                WHERE f.tenant_id = :tenant_id
                AND f.face_embedding IS NOT NULL
                ORDER BY f.face_embedding <=> :embedding::vector
                LIMIT 50
            """

            params = {
                "tenant_id": tenant_id,
                "embedding": str(embedding),
            }

            result = await db.execute(text(sql), params)
            rows = result.fetchall()

            return [
                {
                    "asset_id": row.asset_id,
                    "title": row.title,
                    "asset_type": row.asset_type,
                    "status": row.status,
                    "duration_ms": row.duration_ms,
                    "created_at": row.created_at,
                    "match": MatchInfo(
                        type="face",
                        timecode_ms=row.timecode_ms,
                        person_name=row.person_name,
                        score=float(row.similarity),
                    ),
                    "rank": float(row.similarity),
                }
                for row in rows
                if row.similarity >= 0.5  # Minimum similarity threshold
            ]

        except Exception as e:
            logger.warning(f"Face search failed: {e}")
            return []

    def _merge_results(
        self,
        results_by_asset: dict[UUID, dict[str, Any]],
        new_results: list[dict[str, Any]],
        source_type: str,
    ) -> None:
        """Merge new search results into existing results."""
        for result in new_results:
            asset_id = result["asset_id"]

            if asset_id not in results_by_asset:
                results_by_asset[asset_id] = {
                    "asset_id": asset_id,
                    "title": result.get("title"),
                    "description": result.get("description"),
                    "asset_type": result.get("asset_type"),
                    "status": result.get("status"),
                    "duration_ms": result.get("duration_ms"),
                    "created_at": result.get("created_at"),
                    "thumbnail_url": result.get("thumbnail_url"),
                    "matches": [],
                    "ranks": {},
                }

            results_by_asset[asset_id]["matches"].append(result["match"])
            results_by_asset[asset_id]["ranks"][source_type] = result["rank"]

    def _calculate_rrf_score(self, matches: list[MatchInfo]) -> float:
        """
        Calculate Reciprocal Rank Fusion score.

        RRF(d) = sum(1 / (k + rank(d)))

        This gives higher weight to documents that appear in multiple result lists.
        """
        if not matches:
            return 0.0

        # Sort matches by score to get ranks
        sorted_matches = sorted(matches, key=lambda m: m.score, reverse=True)

        rrf_score = 0.0
        for rank, match in enumerate(sorted_matches, 1):
            rrf_score += 1.0 / (self.rrf_k + rank)

        # Boost by number of matching sources
        source_boost = 1.0 + (len(matches) - 1) * 0.2

        return rrf_score * source_boost

    def _add_filters(
        self,
        sql: str,
        filters: Any,
        params: dict[str, Any],
    ) -> str:
        """Add filter conditions to SQL query."""
        if filters.asset_type:
            sql += " AND a.asset_type = :asset_type"
            params["asset_type"] = filters.asset_type

        if filters.status:
            sql += " AND a.status = :status"
            params["status"] = filters.status

        if filters.date_from:
            sql += " AND a.created_at >= :date_from"
            params["date_from"] = filters.date_from

        if filters.date_to:
            sql += " AND a.created_at <= :date_to"
            params["date_to"] = filters.date_to

        if filters.min_duration_ms:
            sql += " AND a.duration_ms >= :min_duration"
            params["min_duration"] = filters.min_duration_ms

        if filters.max_duration_ms:
            sql += " AND a.duration_ms <= :max_duration"
            params["max_duration"] = filters.max_duration_ms

        return sql

    async def get_suggestions(
        self,
        db: AsyncSession,
        query: str,
        tenant_id: UUID,
        limit: int = 10,
    ) -> list[SearchSuggestion]:
        """Get search suggestions based on partial query."""
        suggestions = []

        # Suggest from keywords
        result = await db.execute(
            text("""
                SELECT keyword, COUNT(*) as count
                FROM asset_keywords
                WHERE tenant_id = :tenant_id
                AND keyword_normalized ILIKE :query
                GROUP BY keyword
                ORDER BY count DESC
                LIMIT :limit
            """),
            {"tenant_id": tenant_id, "query": f"%{query.lower()}%", "limit": limit // 2},
        )

        for row in result.fetchall():
            suggestions.append(SearchSuggestion(
                text=row.keyword,
                type="keyword",
                count=row.count,
            ))

        # Suggest from persons
        result = await db.execute(
            text("""
                SELECT name, appearance_count
                FROM persons
                WHERE tenant_id = :tenant_id
                AND name ILIKE :query
                ORDER BY appearance_count DESC
                LIMIT :limit
            """),
            {"tenant_id": tenant_id, "query": f"%{query}%", "limit": limit // 2},
        )

        for row in result.fetchall():
            suggestions.append(SearchSuggestion(
                text=row.name,
                type="person",
                count=row.appearance_count,
            ))

        return suggestions[:limit]


# Singleton instance
search_service = SearchService()

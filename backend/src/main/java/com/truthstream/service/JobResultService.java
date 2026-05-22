package com.truthstream.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.truthstream.model.Job;
import com.truthstream.model.Verdict;
import com.truthstream.repository.JobRepository;
import com.truthstream.repository.VerdictRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;
import java.util.*;

@Service
@RequiredArgsConstructor
public class JobResultService {

    private final JdbcTemplate jdbcTemplate;
    private final JobRepository jobRepository;
    private final VerdictRepository verdictRepository;
    private final ObjectMapper objectMapper;

    @Transactional(readOnly = true)
    public Map<String, Object> getFullVerdict(UUID jobId, UUID userId) {
        verifyJobAccess(jobId, userId);

        Verdict overall = verdictRepository.findByJobIdAndIsOverallTrue(jobId).orElse(null);
        List<Map<String, Object>> claimRows = jdbcTemplate.queryForList("""
                SELECT c.id AS claim_id, c.text, c.claim_type, c.checkability, c.context_quote,
                       v.verdict, v.confidence, v.reasoning
                FROM claims c
                LEFT JOIN verdicts v ON v.claim_id = c.id AND v.job_id = ?
                WHERE c.job_id = ?
                ORDER BY c.created_at
                """, jobId, jobId);

        List<Map<String, Object>> sourceRows = jdbcTemplate.queryForList("""
                SELECT s.id AS source_id, s.claim_id, s.url, s.title, s.domain, s.snippet,
                       s.stance, s.quality_score, s.fetch_status
                FROM sources s
                JOIN claims c ON c.id = s.claim_id
                WHERE c.job_id = ?
                ORDER BY s.created_at
                """, jobId);

        Map<String, List<Map<String, Object>>> sourcesByClaim = new LinkedHashMap<>();
        for (Map<String, Object> row : sourceRows) {
            String claimId = row.get("claim_id").toString();
            sourcesByClaim.computeIfAbsent(claimId, k -> new ArrayList<>()).add(mapSource(row));
        }

        List<Map<String, Object>> claimVerdicts = new ArrayList<>();
        for (Map<String, Object> row : claimRows) {
            String claimId = row.get("claim_id").toString();
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("claim_id", claimId);
            entry.put("text", row.get("text"));
            entry.put("claim_type", row.get("claim_type"));
            entry.put("checkability", row.get("checkability"));
            entry.put("context_quote", row.get("context_quote"));
            entry.put("verdict", row.get("verdict") != null ? row.get("verdict") : "PENDING");
            entry.put("confidence", row.get("confidence") != null ? row.get("confidence") : 0);
            entry.put("reasoning", row.get("reasoning") != null ? row.get("reasoning") : "");
            entry.put("sources", sourcesByClaim.getOrDefault(claimId, List.of()));
            claimVerdicts.add(entry);
        }

        Map<String, Object> bias = loadBias(jobId);
        Map<String, Object> article = loadArticle(jobId);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("job_id", jobId);
        response.put("overall_verdict", overall != null ? overall.getVerdict() : "PENDING");
        response.put("overall_confidence", overall != null && overall.getConfidence() != null
                ? overall.getConfidence() : 0);
        response.put("overall_summary", overall != null && overall.getReasoning() != null
                ? overall.getReasoning() : "");
        response.put("bias", bias);
        response.put("article", article);
        response.put("claim_verdicts", claimVerdicts);
        return response;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getSourcesByClaim(UUID jobId, UUID userId) {
        verifyJobAccess(jobId, userId);

        List<Map<String, Object>> sourceRows = jdbcTemplate.queryForList("""
                SELECT s.id AS source_id, s.claim_id, s.url, s.title, s.domain, s.snippet,
                       s.stance, s.quality_score, s.fetch_status
                FROM sources s
                JOIN claims c ON c.id = s.claim_id
                WHERE c.job_id = ?
                ORDER BY s.created_at
                """, jobId);

        Map<String, List<Map<String, Object>>> sourcesByClaim = new LinkedHashMap<>();
        for (Map<String, Object> row : sourceRows) {
            String claimId = row.get("claim_id").toString();
            sourcesByClaim.computeIfAbsent(claimId, k -> new ArrayList<>()).add(mapSource(row));
        }

        return Map.of("job_id", jobId, "sources_by_claim", sourcesByClaim);
    }

    private Map<String, Object> mapSource(Map<String, Object> row) {
        Map<String, Object> s = new LinkedHashMap<>();
        s.put("source_id", row.get("source_id").toString());
        s.put("url", row.get("url"));
        s.put("title", row.get("title"));
        s.put("domain", row.get("domain"));
        s.put("snippet", row.get("snippet"));
        s.put("stance", row.get("stance"));
        s.put("quality_score", toDouble(row.get("quality_score")));
        s.put("fetch_status", row.get("fetch_status"));
        return s;
    }

    private Map<String, Object> loadBias(UUID jobId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("""
                SELECT bias_score, bias_direction, framing_flags, loaded_terms, summary
                FROM bias_results WHERE job_id = ? LIMIT 1
                """, jobId);
        if (rows.isEmpty()) {
            return null;
        }
        Map<String, Object> row = rows.getFirst();
        Map<String, Object> bias = new LinkedHashMap<>();
        bias.put("bias_score", row.get("bias_score"));
        bias.put("bias_direction", row.get("bias_direction"));
        bias.put("summary", row.get("summary"));
        bias.put("loaded_terms", parseStringArray(row.get("loaded_terms")));
        bias.put("framing_flags", parseFramingFlags(row.get("framing_flags")));
        return bias;
    }

    private Map<String, Object> loadArticle(UUID jobId) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("""
                SELECT a.id, a.url, a.truncated
                FROM jobs j
                JOIN articles a ON a.id = j.article_id
                WHERE j.id = ?
                """, jobId);
        if (rows.isEmpty()) {
            return null;
        }
        Map<String, Object> row = rows.getFirst();
        return Map.of(
                "id", row.get("id").toString(),
                "url", row.get("url") != null ? row.get("url") : "",
                "truncated", Boolean.TRUE.equals(row.get("truncated"))
        );
    }

    private List<String> parseStringArray(Object value) {
        if (value == null) {
            return List.of();
        }
        if (value instanceof String[] arr) {
            return Arrays.asList(arr);
        }
        if (value instanceof List<?> list) {
            return list.stream().map(Object::toString).toList();
        }
        return List.of(value.toString());
    }

    private List<Map<String, Object>> parseFramingFlags(Object value) {
        if (value == null) {
            return List.of();
        }
        try {
            String json = value instanceof String s ? s : objectMapper.writeValueAsString(value);
            return objectMapper.readValue(json, new TypeReference<>() {});
        } catch (Exception e) {
            return List.of();
        }
    }

    private double toDouble(Object value) {
        if (value == null) {
            return 0.0;
        }
        if (value instanceof BigDecimal bd) {
            return bd.doubleValue();
        }
        if (value instanceof Number n) {
            return n.doubleValue();
        }
        return Double.parseDouble(value.toString());
    }

    private void verifyJobAccess(UUID jobId, UUID userId) {
        Job job = jobRepository.findById(jobId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Job not found"));
        if (!job.getUser().getId().equals(userId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Access denied");
        }
    }
}

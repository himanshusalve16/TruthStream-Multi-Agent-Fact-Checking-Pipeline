package com.truthstream.controller;

import com.truthstream.model.Verdict;
import com.truthstream.repository.VerdictRepository;
import com.truthstream.service.JobService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/jobs")
@RequiredArgsConstructor
public class VerdictController {

    private final VerdictRepository verdictRepository;
    private final JobService jobService;

    @GetMapping("/{jobId}/verdict")
    public ResponseEntity<Map<String, Object>> getVerdict(
            @PathVariable UUID jobId,
            Authentication auth) {

        UUID userId = (UUID) auth.getPrincipal();
        // Verify ownership
        jobService.getJob(jobId, userId);

        Verdict overall = verdictRepository.findByJobIdAndIsOverallTrue(jobId)
                .orElse(null);
        List<Verdict> claimVerdicts = verdictRepository.findByJobIdAndIsOverallFalse(jobId);

        return ResponseEntity.ok(Map.of(
                "job_id", jobId,
                "overall_verdict", overall != null ? overall.getVerdict() : "PENDING",
                "overall_confidence", overall != null && overall.getConfidence() != null
                        ? overall.getConfidence() : 0,
                "overall_summary", overall != null && overall.getReasoning() != null
                        ? overall.getReasoning() : "",
                "claim_verdicts", claimVerdicts.stream().map(v -> Map.of(
                        "claim_id", v.getClaimId() != null ? v.getClaimId() : "",
                        "verdict", v.getVerdict(),
                        "confidence", v.getConfidence() != null ? v.getConfidence() : 0,
                        "reasoning", v.getReasoning() != null ? v.getReasoning() : ""
                )).toList()
        ));
    }
}

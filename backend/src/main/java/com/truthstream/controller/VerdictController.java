package com.truthstream.controller;

import com.truthstream.service.JobResultService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/jobs")
@RequiredArgsConstructor
public class VerdictController {

    private final JobResultService jobResultService;

    @GetMapping("/{jobId}/verdict")
    public ResponseEntity<Map<String, Object>> getVerdict(
            @PathVariable UUID jobId,
            Authentication auth) {

        UUID userId = (UUID) auth.getPrincipal();
        return ResponseEntity.ok(jobResultService.getFullVerdict(jobId, userId));
    }

    @GetMapping("/{jobId}/sources")
    public ResponseEntity<Map<String, Object>> getSources(
            @PathVariable UUID jobId,
            Authentication auth) {

        UUID userId = (UUID) auth.getPrincipal();
        return ResponseEntity.ok(jobResultService.getSourcesByClaim(jobId, userId));
    }
}

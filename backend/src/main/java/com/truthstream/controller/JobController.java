package com.truthstream.controller;

import com.truthstream.dto.JobRequest;
import com.truthstream.dto.JobResponse;
import com.truthstream.service.JobService;
import com.truthstream.service.SseService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/jobs")
@RequiredArgsConstructor
@Slf4j
public class JobController {

    private final JobService jobService;
    private final SseService sseService;

    @PostMapping
    public ResponseEntity<Map<String, Object>> createJob(
            @Valid @RequestBody JobRequest request,
            Authentication auth) {

        UUID userId = (UUID) auth.getPrincipal();
        JobResponse job = jobService.createJob(userId, request);

        return ResponseEntity.status(HttpStatus.ACCEPTED).body(Map.of(
                "job_id", job.getJobId(),
                "status", job.getStatus(),
                "created_at", job.getCreatedAt()
        ));
    }

    @GetMapping("/{jobId}")
    public ResponseEntity<JobResponse> getJob(
            @PathVariable UUID jobId,
            Authentication auth) {

        UUID userId = (UUID) auth.getPrincipal();
        return ResponseEntity.ok(jobService.getJob(jobId, userId));
    }

    @GetMapping
    public ResponseEntity<Map<String, Object>> listJobs(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size,
            Authentication auth) {

        UUID userId = (UUID) auth.getPrincipal();
        return ResponseEntity.ok(jobService.listJobs(userId, page, Math.min(size, 100)));
    }

    @GetMapping(value = "/{jobId}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamJob(
            @PathVariable UUID jobId,
            Authentication auth) {

        UUID userId = (UUID) auth.getPrincipal();
        // Verify the job belongs to this user before subscribing
        jobService.getJob(jobId, userId);

        log.info("SSE stream opened for job {} by user {}", jobId, userId);
        return sseService.register(jobId);
    }
}

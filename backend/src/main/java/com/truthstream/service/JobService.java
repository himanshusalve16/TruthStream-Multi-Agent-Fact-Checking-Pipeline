package com.truthstream.service;

import com.truthstream.dto.JobRequest;
import com.truthstream.dto.JobResponse;
import com.truthstream.model.Job;
import com.truthstream.model.User;
import com.truthstream.repository.JobRepository;
import com.truthstream.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class JobService {

    private final JobRepository jobRepository;
    private final UserRepository userRepository;
    private final FastApiClient fastApiClient;
    private final RateLimitService rateLimitService;

    /**
     * Create a new fact-checking job. Enforces rate limits and duplicate URL detection.
     */
    @Transactional
    public JobResponse createJob(UUID userId, JobRequest request) {
        // Validate input (before rate limit so bad requests don't count)
        if ("url".equals(request.getInputType()) && (request.getUrl() == null || request.getUrl().isBlank())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "URL is required for input_type=url");
        }
        if ("text".equals(request.getInputType()) && (request.getText() == null || request.getText().isBlank())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Text is required for input_type=text");
        }

        // Duplicate URL detection: same user, same URL, completed in last 24h
        if ("url".equals(request.getInputType()) && request.getUrl() != null) {
            Optional<Job> cached = jobRepository.findFirstByUserIdAndStatusAndInputUrlAndCreatedAtAfter(
                    userId,
                    "COMPLETE",
                    request.getUrl(),
                    OffsetDateTime.now().minusHours(24));

            if (cached.isPresent()) {
                log.info("Returning cached job {} for URL {}", cached.get().getId(), request.getUrl());
                return toJobResponse(cached.get());
            }
        }

        User user = userRepository.getReferenceById(userId);
        Job job = Job.builder()
                .user(user)
                .status("PENDING")
                .inputUrl(request.getUrl())
                .inputText(request.getText())
                .build();

        rateLimitService.checkJobRateLimit(userId);
        job = jobRepository.save(job);
        rateLimitService.recordJobSubmission(userId);

        // Dispatch to FastAPI asynchronously after transaction commits to prevent race conditions
        final UUID jobId = job.getId();
        final JobResponse response = toJobResponse(job);

        if (org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive()) {
            org.springframework.transaction.support.TransactionSynchronizationManager.registerSynchronization(
                new org.springframework.transaction.support.TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        log.info("Transaction committed. Dispatching job {} to FastAPI...", jobId);
                        fastApiClient.dispatchJob(
                                jobId, userId,
                                request.getInputType(),
                                request.getUrl(),
                                request.getText()
                        );
                    }
                }
            );
        } else {
            log.info("No active transaction. Dispatching job {} to FastAPI immediately...", jobId);
            fastApiClient.dispatchJob(
                    jobId, userId,
                    request.getInputType(),
                    request.getUrl(),
                    request.getText()
            );
        }

        log.info("Created job {} for user {}", jobId, userId);
        return response;
    }

    public JobResponse getJob(UUID jobId, UUID userId) {
        Job job = jobRepository.findById(jobId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Job not found"));

        if (!job.getUser().getId().equals(userId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Access denied");
        }

        return toJobResponse(job);
    }

    public Map<String, Object> listJobs(UUID userId, int page, int size) {
        Page<Job> jobs = jobRepository.findByUserIdOrderByCreatedAtDesc(
                userId, PageRequest.of(page - 1, size));

        List<JobResponse> jobResponses = jobs.getContent().stream()
                .map(this::toJobResponse)
                .toList();

        return Map.of(
                "jobs", jobResponses,
                "total", jobs.getTotalElements(),
                "page", page,
                "page_size", size
        );
    }

    private JobResponse toJobResponse(Job job) {
        return JobResponse.builder()
                .jobId(job.getId())
                .status(job.getStatus())
                .createdAt(job.getCreatedAt())
                .updatedAt(job.getUpdatedAt())
                .inputUrl(job.getInputUrl())
                .errorMessage(job.getErrorMessage())
                .build();
    }
}

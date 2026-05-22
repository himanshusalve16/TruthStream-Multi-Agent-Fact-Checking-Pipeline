package com.truthstream.service;

import com.truthstream.dto.JobRequest;
import com.truthstream.dto.JobResponse;
import com.truthstream.model.Job;
import com.truthstream.model.User;
import com.truthstream.repository.JobRepository;
import com.truthstream.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
@Slf4j
public class JobService {

    private final JobRepository jobRepository;
    private final UserRepository userRepository;
    private final FastApiClient fastApiClient;
    private final RedisTemplate<String, String> redisTemplate;

    @Value("${app.rate-limit.max-jobs-per-hour:10}")
    private int maxJobsPerHour;

    /**
     * Create a new fact-checking job. Enforces rate limits and duplicate URL detection.
     */
    @Transactional
    public JobResponse createJob(UUID userId, JobRequest request) {
        // Rate limit check
        checkRateLimit(userId);

        // Validate input
        if ("url".equals(request.getInputType()) && (request.getUrl() == null || request.getUrl().isBlank())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "URL is required for input_type=url");
        }
        if ("text".equals(request.getInputType()) && (request.getText() == null || request.getText().isBlank())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Text is required for input_type=text");
        }

        // Duplicate URL detection: same user, same URL, completed in last 24h
        if ("url".equals(request.getInputType()) && request.getUrl() != null) {
            Optional<Job> cached = jobRepository.findRecentCompleteByUserAndUrl(
                    userId,
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

        job = jobRepository.save(job);
        incrementRateLimit(userId);

        // Dispatch to FastAPI asynchronously
        final UUID jobId = job.getId();
        fastApiClient.dispatchJob(
                jobId, userId,
                request.getInputType(),
                request.getUrl(),
                request.getText()
        );

        log.info("Created job {} for user {}", jobId, userId);
        return toJobResponse(job);
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

    private void checkRateLimit(UUID userId) {
        String key = "ratelimit:" + userId;
        Long count = redisTemplate.opsForValue().increment(key);
        if (count == 1) {
            redisTemplate.expire(key, 1, TimeUnit.HOURS);
        }
        if (count != null && count > maxJobsPerHour) {
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,
                    "Rate limit exceeded: max " + maxJobsPerHour + " jobs per hour");
        }
    }

    private void incrementRateLimit(UUID userId) {
        // Already incremented in checkRateLimit
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

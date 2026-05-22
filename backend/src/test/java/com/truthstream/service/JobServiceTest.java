package com.truthstream.service;

import com.truthstream.dto.JobRequest;
import com.truthstream.dto.JobResponse;
import com.truthstream.model.Job;
import com.truthstream.model.User;
import com.truthstream.repository.JobRepository;
import com.truthstream.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.server.ResponseStatusException;

import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class JobServiceTest {

    @Mock
    private JobRepository jobRepository;
    @Mock
    private UserRepository userRepository;
    @Mock
    private FastApiClient fastApiClient;
    @Mock
    private RateLimitService rateLimitService;

    @InjectMocks
    private JobService jobService;

    @Test
    void createJob_returnsCachedJobForDuplicateUrl() {
        UUID userId = UUID.randomUUID();
        JobRequest request = new JobRequest();
        request.setInputType("url");
        request.setUrl("https://example.com/article");

        Job cached = Job.builder()
                .id(UUID.randomUUID())
                .status("COMPLETE")
                .inputUrl(request.getUrl())
                .createdAt(OffsetDateTime.now())
                .updatedAt(OffsetDateTime.now())
                .build();

        when(jobRepository.findRecentCompleteByUserAndUrl(eq(userId), eq(request.getUrl()), any()))
                .thenReturn(Optional.of(cached));

        JobResponse response = jobService.createJob(userId, request);

        assertEquals(cached.getId(), response.getJobId());
        verify(jobRepository, never()).save(any());
        verify(fastApiClient, never()).dispatchJob(any(), any(), any(), any(), any());
    }

    @Test
    void createJob_rejectsMissingUrl() {
        UUID userId = UUID.randomUUID();
        JobRequest request = new JobRequest();
        request.setInputType("url");

        assertThrows(ResponseStatusException.class, () -> jobService.createJob(userId, request));
        verify(rateLimitService, never()).recordJobSubmission(any());
    }
}

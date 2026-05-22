package com.truthstream.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;

@Service
@Slf4j
public class FastApiClient {

    private final WebClient webClient;
    private final String internalSecret;
    private final int timeoutSeconds;

    public FastApiClient(
            @Value("${app.fastapi.base-url}") String baseUrl,
            @Value("${app.internal.api-secret}") String internalSecret,
            @Value("${app.fastapi.timeout-seconds:30}") int timeoutSeconds) {
        this.internalSecret = internalSecret;
        this.timeoutSeconds = timeoutSeconds;
        this.webClient = WebClient.builder()
                .baseUrl(baseUrl)
                .defaultHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .build();
    }

    /**
     * Dispatch a job to the FastAPI AI service. Non-blocking fire-and-forget.
     */
    public void dispatchJob(UUID jobId, UUID userId, String inputType, String url, String text) {
        Map<String, Object> body = new java.util.HashMap<>();
        body.put("job_id", jobId.toString());
        body.put("user_id", userId.toString());
        body.put("input_type", inputType);
        if (url != null) body.put("url", url);
        if (text != null) body.put("text", text);

        webClient.post()
                .uri("/internal/jobs")
                .header("X-Internal-Secret", internalSecret)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .onErrorResume(e -> {
                    log.error("Failed to dispatch job {} to FastAPI: {}", jobId, e.getMessage());
                    return Mono.empty();
                })
                .subscribe(response ->
                        log.info("Job {} dispatched to FastAPI, status: {}",
                                jobId, response != null ? response.getStatusCode() : "null")
                );
    }
}

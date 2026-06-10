package com.truthstream.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;

/**
 * HTTP client for the FastAPI AI Execution Service.
 *
 * <p>URL Resolution: uses {@code FASTAPI_BASE_URL} env var directly.
 * Direct service-to-service communication on Render using static environment
 * variables — no service registry required.
 *
 * <p>Set {@code FASTAPI_BASE_URL} to the full Render URL of the AI service,
 * e.g. {@code https://truthstream-ai.onrender.com}.
 */
@Service
@Slf4j
public class FastApiClient {

    private final WebClient webClient;
    private final String baseUrl;
    private final String internalSecret;
    private final int timeoutSeconds;

    public FastApiClient(
            @Value("${app.fastapi.base-url}") String baseUrl,
            @Value("${app.internal.api-secret}") String internalSecret,
            @Value("${app.fastapi.timeout-seconds:30}") int timeoutSeconds) {
        this.baseUrl = normalizeUrl(baseUrl);
        this.internalSecret = internalSecret;
        this.timeoutSeconds = timeoutSeconds;

        this.webClient = WebClient.builder()
                .defaultHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .build();

        log.info("FastApiClient initialized. AI service URL: {}", this.baseUrl);
    }

    // ── URL Normalization ─────────────────────────────────────────────────────

    /**
     * Normalize a raw URL string:
     * <ul>
     *   <li>Strips trailing slashes</li>
     *   <li>Cleans nested schemes (http://https://...)</li>
     *   <li>Prepends http:// if no scheme present</li>
     *   <li>Forces HTTPS and strips port for *.onrender.com hosts</li>
     * </ul>
     */
    public static String normalizeUrl(String url) {
        if (url == null) {
            return null;
        }
        String normalized = url.trim();

        // Remove trailing slashes
        while (normalized.endsWith("/")) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }

        // Clean up nested schemes like http://https://, http://http://, https://https://, or https://http://
        if (normalized.startsWith("http://https://")) {
            normalized = normalized.substring(7);
        } else if (normalized.startsWith("http://http://")) {
            normalized = normalized.substring(7);
        } else if (normalized.startsWith("https://https://")) {
            normalized = normalized.substring(8);
        } else if (normalized.startsWith("https://http://")) {
            normalized = normalized.substring(8);
        }

        // If it does not start with http:// or https://, prepend http://
        if (!normalized.startsWith("http://") && !normalized.startsWith("https://")) {
            normalized = "http://" + normalized;
        }

        // Remove duplicate ports if they were appended at the end (e.g. host:10000:10000)
        normalized = normalized.replaceAll(":(\\d+):\\1$", ":$1");

        // Render deployment specific normalization: force HTTPS and strip port
        if (normalized.contains(".onrender.com")) {
            if (normalized.startsWith("http://")) {
                normalized = "https://" + normalized.substring(7);
            }
            normalized = normalized.replaceAll(":\\d+$", "");
        }

        return normalized;
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /**
     * Dispatch a job to the FastAPI AI service. Non-blocking fire-and-forget.
     * The AI service will process the job asynchronously and publish events
     * back to the Gateway via Redis Pub/Sub.
     */
    public void dispatchJob(UUID jobId, UUID userId, String inputType, String url, String text) {
        Map<String, Object> body = new java.util.HashMap<>();
        body.put("job_id", jobId.toString());
        body.put("user_id", userId.toString());
        body.put("input_type", inputType);
        if (url != null) body.put("url", url);
        if (text != null) body.put("text", text);

        webClient.post()
                .uri(baseUrl + "/internal/jobs")
                .header("X-Internal-Secret", internalSecret)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .onErrorResume(e -> {
                    log.error("Failed to dispatch job {} to AI service at {}: {}", jobId, baseUrl, e.getMessage());
                    return Mono.empty();
                })
                .subscribe(response ->
                        log.info("Job {} dispatched to AI service ({}), status: {}",
                                jobId, baseUrl, response != null ? response.getStatusCode() : "null")
                );
    }

    /**
     * Check if the FastAPI service is ready.
     */
    public Mono<String> checkReady() {
        return webClient.get()
                .uri(baseUrl + "/ready")
                .retrieve()
                .bodyToMono(Map.class)
                .map(responseBody -> {
                    if (responseBody != null && "ready".equals(responseBody.get("status"))) {
                        return "ready";
                    }
                    if (responseBody != null && "waking".equals(responseBody.get("status"))) {
                        return "waking";
                    }
                    return "sleeping";
                })
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(e -> {
                    log.debug("AI service /ready not responding at {}: {}", baseUrl, e.getMessage());
                    return Mono.just("sleeping");
                });
    }

    /**
     * Check if the FastAPI service is healthy.
     */
    public Mono<String> checkHealth() {
        return webClient.get()
                .uri(baseUrl + "/health")
                .retrieve()
                .bodyToMono(Map.class)
                .map(responseBody -> {
                    if (responseBody != null) {
                        String status = (String) responseBody.get("status");
                        if ("ok".equals(status)) {
                            return "healthy";
                        } else if ("degraded".equals(status)) {
                            return "degraded";
                        }
                    }
                    return "sleeping";
                })
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(e -> {
                    log.debug("AI service /health not responding at {}: {}", baseUrl, e.getMessage());
                    return Mono.just("sleeping");
                });
    }
}

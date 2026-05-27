package com.truthstream.controller;

import com.truthstream.service.FastApiClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.util.Map;

/**
 * Lightweight system health and readiness endpoints.
 *
 * <h2>Endpoint contract</h2>
 * <ul>
 *   <li>{@code GET /api/health} — <strong>Gateway self-check only</strong>.
 *       Returns immediately with {@code {"status":"ok"}} without probing the
 *       AI service, Redis, Eureka, or any external dependency. Used by the
 *       frontend status badge. Must always be fast (≤5 ms).</li>
 *
 *   <li>{@code GET /api/ready} — Deep readiness probe that checks whether the
 *       AI service is currently reachable and ready to process jobs. Used
 *       for diagnostic tooling only — the frontend does NOT poll this endpoint.
 *       May return 503 while the AI service is cold-starting.</li>
 * </ul>
 *
 * <h2>Why /api/health must not call the AI service</h2>
 * The frontend status badge polls /api/health every 30 seconds to show
 * "AI Service Online" / "Warming Up". If /api/health were to proxy the
 * AI service health check, a cold-starting or sleeping AI service would
 * cause the gateway to return 503 — and the badge would show "Warming Up"
 * indefinitely even though the <em>gateway</em> is fully healthy.
 *
 * <p>The correct mental model: /api/health answers "is the gateway alive?"
 * not "is the entire distributed system healthy?".
 */
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Slf4j
public class SystemHealthController {

    private final FastApiClient fastApiClient;

    /**
     * Lightweight gateway health check.
     *
     * <p>Returns {@code {"status":"ok"}} immediately. No I/O, no DB, no Redis,
     * no Eureka, no AI service probing. The frontend uses this endpoint to
     * determine the status badge ("AI Service Online" vs "Warming Up").
     *
     * <p>Returns 200 OK as long as the Spring Boot gateway itself is running.
     * An AI service outage does NOT affect this response — the gateway still
     * routes jobs via Redis and returns verdicts via SSE.
     */
    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> getSystemHealth() {
        return ResponseEntity.ok(Map.of("status", "ok"));
    }

    /**
     * Deep AI service readiness probe.
     *
     * <p>Proxies a health check to the FastAPI AI service. Returns:
     * <ul>
     *   <li>200 {@code {"status":"ready"}} — AI service is up and healthy</li>
     *   <li>200 {@code {"status":"degraded"}} — AI service is up but at reduced capacity</li>
     *   <li>503 {@code {"status":"sleeping"}} — AI service unreachable (cold-starting or sleeping)</li>
     * </ul>
     *
     * <p><strong>Not polled by the frontend.</strong> Use this endpoint for:
     * deployment verification, uptime monitors, manual diagnostics.
     */
    @GetMapping("/ready")
    public Mono<ResponseEntity<Map<String, String>>> getSystemReady() {
        return fastApiClient.checkHealth()
                .map(status -> {
                    if ("healthy".equals(status)) {
                        return ResponseEntity.ok(Map.of("status", "ready"));
                    } else if ("degraded".equals(status)) {
                        return ResponseEntity.ok(
                                Map.of("status", "degraded", "details", "AI service is running at reduced capacity"));
                    } else {
                        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                                .body(Map.of("status", "sleeping", "details", "AI service is offline or cold-starting"));
                    }
                })
                .onErrorResume(e -> {
                    log.warn("Failed to check AI service readiness: {}", e.getMessage());
                    return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(Map.of("status", "sleeping", "details", e.getMessage())));
                });
    }
}

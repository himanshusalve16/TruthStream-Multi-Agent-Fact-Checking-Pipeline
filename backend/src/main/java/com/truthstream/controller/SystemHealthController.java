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

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Slf4j
public class SystemHealthController {

    private final FastApiClient fastApiClient;

    @GetMapping("/ready")
    public Mono<ResponseEntity<Map<String, String>>> getSystemReady() {
        return fastApiClient.checkReady()
                .map(status -> {
                    if ("ready".equals(status)) {
                        return ResponseEntity.ok(Map.of("status", "ready"));
                    } else if ("waking".equals(status)) {
                        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                                .body(Map.of("status", "waking", "details", "AI service is booting and warming up"));
                    } else {
                        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                                .body(Map.of("status", "sleeping", "details", "AI service is offline or sleeping"));
                    }
                })
                .onErrorResume(e -> {
                    log.warn("Failed to check FastAPI readiness: {}", e.getMessage());
                    return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(Map.of("status", "sleeping", "details", e.getMessage())));
                });
    }
}

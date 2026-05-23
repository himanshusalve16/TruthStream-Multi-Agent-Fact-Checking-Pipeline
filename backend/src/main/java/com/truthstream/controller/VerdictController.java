package com.truthstream.controller;

import com.truthstream.service.JobResultService;
import com.truthstream.model.User;
import com.truthstream.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/jobs")
@RequiredArgsConstructor
public class VerdictController {

    private final JobResultService jobResultService;
    private final UserRepository userRepository;

    private UUID getDevUserId() {
        return userRepository.findByEmail("dev@truthstream.local")
                .map(User::getId)
                .orElseGet(() -> {
                    User u = new User();
                    u.setEmail("dev@truthstream.local");
                    u.setPasswordHash("none");
                    return userRepository.save(u).getId();
                });
    }

    @GetMapping("/{jobId}/verdict")
    public ResponseEntity<Map<String, Object>> getVerdict(
            @PathVariable UUID jobId) {

        UUID userId = getDevUserId();
        return ResponseEntity.ok(jobResultService.getFullVerdict(jobId, userId));
    }

    @GetMapping("/{jobId}/sources")
    public ResponseEntity<Map<String, Object>> getSources(
            @PathVariable UUID jobId) {

        UUID userId = getDevUserId();
        return ResponseEntity.ok(jobResultService.getSourcesByClaim(jobId, userId));
    }
}

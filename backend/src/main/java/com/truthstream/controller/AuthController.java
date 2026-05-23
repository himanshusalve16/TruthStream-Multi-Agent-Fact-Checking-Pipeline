package com.truthstream.controller;

import com.truthstream.dto.AuthRequest;
import com.truthstream.dto.AuthResponse;
import com.truthstream.service.AuthService;
import com.truthstream.service.RateLimitService;
import com.truthstream.util.ClientIpResolver;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
@Slf4j
public class AuthController {

    private final AuthService authService;
    private final RateLimitService rateLimitService;

    @PostMapping("/register")
    public ResponseEntity<Map<String, Object>> register(
            @Valid @RequestBody AuthRequest request,
            HttpServletRequest httpRequest) {
        String clientIp = ClientIpResolver.resolve(httpRequest);
        rateLimitService.checkAuthRateLimit(clientIp);
        rateLimitService.recordAuthAttempt(clientIp);
        try {
            AuthResponse response = authService.register(request);
            return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                    "user_id", response.getUserId(),
                    "email", response.getEmail(),
                    "access_token", response.getAccessToken(),
                    "token_type", response.getTokenType(),
                    "expires_in", response.getExpiresIn()
            ));
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, e.getMessage());
        }
    }

    @PostMapping("/login")
    public ResponseEntity<Map<String, Object>> login(
            @Valid @RequestBody AuthRequest request,
            HttpServletRequest httpRequest) {
        String clientIp = ClientIpResolver.resolve(httpRequest);
        rateLimitService.checkAuthRateLimit(clientIp);
        rateLimitService.recordAuthAttempt(clientIp);
        try {
            AuthResponse response = authService.login(request);
            return ResponseEntity.ok(Map.of(
                    "access_token", response.getAccessToken(),
                    "token_type", "Bearer",
                    "expires_in", response.getExpiresIn()
            ));
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, e.getMessage());
        }
    }
}

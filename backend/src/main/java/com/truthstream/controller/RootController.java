package com.truthstream.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
public class RootController {

    @GetMapping("/")
    public ResponseEntity<Map<String, String>> getRoot() {
        return ResponseEntity.ok(Map.of(
                "service", "truthstream-backend",
                "status", "online"
        ));
    }

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> getHealth() {
        return ResponseEntity.ok(Map.of(
                "status", "ok"
        ));
    }
}

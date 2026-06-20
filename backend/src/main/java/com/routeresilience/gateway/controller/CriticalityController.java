package com.routeresilience.gateway.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.routeresilience.gateway.service.ComputeClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Public API. Mirrors the compute service's surface so the dashboard can point at either one,
 * but everything here is cached and validated. This is the URL the browser actually hits in
 * the full architecture.
 */
@RestController
@RequestMapping("/api")
public class CriticalityController {

    private final ComputeClient compute;

    public CriticalityController(ComputeClient compute) {
        this.compute = compute;
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of("gateway", "ok", "compute", compute.health());
    }

    @GetMapping("/criticality")
    public JsonNode criticality(
            @RequestParam(defaultValue = "sample:koramangala") String source,
            @RequestParam(defaultValue = "length") String weight) {
        return compute.criticality(source, weight);
    }

    @GetMapping("/impact")
    public JsonNode impact(
            @RequestParam int u,
            @RequestParam int v,
            @RequestParam(defaultValue = "sample:koramangala") String source,
            @RequestParam(defaultValue = "length") String weight) {
        return compute.impact(u, v, source, weight);
    }

    @GetMapping("/robustness")
    public JsonNode robustness(
            @RequestParam(defaultValue = "sample:koramangala") String source,
            @RequestParam(defaultValue = "length") String weight,
            @RequestParam(defaultValue = "16") int steps) {
        return compute.robustness(source, weight, steps);
    }
}

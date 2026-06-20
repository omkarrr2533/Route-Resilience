package com.routeresilience.gateway;

import com.routeresilience.gateway.config.ComputeProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.cache.annotation.EnableCaching;

/**
 * API gateway for Route Resilience.
 *
 * <p>The heavy graph science lives in the Python compute service; this layer exists for the
 * things the JVM does well and the plan calls for (§3): caching expensive criticality
 * results, shielding the browser from minutes-long computations, validating requests, and —
 * later — async job orchestration. Computing betweenness on a full city graph can take
 * minutes, so the first request pays that cost once and every repeat is served from cache.
 */
@SpringBootApplication
@EnableCaching
@EnableConfigurationProperties(ComputeProperties.class)
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}

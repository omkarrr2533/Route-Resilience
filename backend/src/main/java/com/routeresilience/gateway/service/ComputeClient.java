package com.routeresilience.gateway.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.routeresilience.gateway.config.CacheConfig;
import com.routeresilience.gateway.config.ComputeProperties;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

/**
 * Talks to the Python compute service over its internal REST API.
 *
 * <p>We pass the JSON straight through as a {@link JsonNode} rather than re-modelling the
 * GeoJSON schema in Java — the gateway's job here is orchestration and caching, not
 * reshaping a payload the frontend already understands. The two genuinely expensive calls
 * (criticality, robustness) are cached on their arguments; impact is cheap and per-edge, so
 * it's a straight pass-through.
 */
@Service
public class ComputeClient {

    private final RestClient http;

    public ComputeClient(ComputeProperties props) {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout((int) props.connectTimeout().toMillis());
        factory.setReadTimeout((int) props.readTimeout().toMillis());
        this.http = RestClient.builder()
                .baseUrl(props.baseUrl())
                .requestFactory(factory)
                .build();
    }

    @Cacheable(cacheNames = CacheConfig.CRITICALITY, key = "#source + '|' + #weight")
    public JsonNode criticality(String source, String weight) {
        return get("/api/criticality", uri -> uri.queryParam("source", source).queryParam("weight", weight));
    }

    public JsonNode impact(int u, int v, String source, String weight) {
        return get("/api/impact", uri -> uri
                .queryParam("u", u).queryParam("v", v)
                .queryParam("source", source).queryParam("weight", weight));
    }

    @Cacheable(cacheNames = CacheConfig.ROBUSTNESS, key = "#source + '|' + #weight + '|' + #steps")
    public JsonNode robustness(String source, String weight, int steps) {
        return get("/api/robustness", uri -> uri
                .queryParam("source", source).queryParam("weight", weight).queryParam("steps", steps));
    }

    public JsonNode health() {
        return get("/api/health", uri -> uri);
    }

    private JsonNode get(String path, java.util.function.UnaryOperator<org.springframework.web.util.UriBuilder> query) {
        return http.get()
                .uri(uri -> query.apply(uri.path(path)).build())
                .retrieve()
                // Surface the compute service's own 4xx (e.g. unknown sample) instead of
                // letting it bubble up as an opaque 500 from the gateway.
                .onStatus(HttpStatusCode::is4xxClientError, (req, res) -> {
                    throw new ResponseStatusException(res.getStatusCode(), "compute service rejected the request");
                })
                .body(JsonNode.class);
    }
}

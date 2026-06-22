package com.routeresilience.gateway.jobs;

import com.fasterxml.jackson.databind.JsonNode;
import com.routeresilience.gateway.service.ComputeClient;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The work behind an approximate-betweenness job: pull Monte Carlo batches from the compute
 * service and fold them into one progressively-tighter estimate.
 *
 * <p>Each batch is an independent sample of {@code batchSamples} sources, so averaging batches
 * (weighted by their sample counts) is statistically identical to one larger run — which is
 * what lets the gateway stream progress and stop the instant the certified ε meets the target.
 * This is the orchestration the Spring layer is for: the heavy SSSP math stays in Python; the
 * gateway aggregates, tracks convergence, and bounds the work.
 */
public class ApproxBetweennessJob implements Runnable {

    private final Job job;
    private final ApproxBetweennessRequest req;
    private final ComputeClient compute;

    public ApproxBetweennessJob(Job job, ApproxBetweennessRequest req, ComputeClient compute) {
        this.job = job;
        this.req = req;
        this.compute = compute;
    }

    @Override
    public void run() {
        try {
            job.running();

            Map<String, Double> weightedSum = new HashMap<>();   // edge -> Σ (b̂_batch · samples)
            Map<String, int[]> endpoints = new HashMap<>();      // edge -> (u, v)
            long totalSamples = 0;
            int batches = 0;
            int m = 0, n = 0;
            int targetSamples = -1;
            int seed = 0;

            while (true) {
                JsonNode resp = compute.sampleBatch(req.source(), req.weight(), req.batchSamples(), seed++);
                JsonNode meta = resp.get("meta");
                int batchSamples = meta.get("samples").asInt();
                m = meta.get("m").asInt();
                n = meta.get("n").asInt();
                if (targetSamples < 0) {
                    targetSamples = Bounds.sampleSize(m, req.eps(), req.delta());
                }

                for (JsonNode e : resp.get("edges")) {
                    int u = e.get("u").asInt();
                    int v = e.get("v").asInt();
                    String key = u + "-" + v;
                    weightedSum.merge(key, e.get("b").asDouble() * batchSamples, Double::sum);
                    endpoints.putIfAbsent(key, new int[]{u, v});
                }

                totalSamples += batchSamples;
                batches++;
                double currentEps = Bounds.achievedEpsilon(m, totalSamples, req.delta());
                double pct = Math.min(0.99, (double) totalSamples / targetSamples);
                job.advance(pct, totalSamples, targetSamples, currentEps, req.eps(), batches);

                if (currentEps <= req.eps() || totalSamples >= req.maxSamples()) {
                    break;
                }
            }

            job.succeed(finalize(weightedSum, endpoints, totalSamples, batches, m, n), summary(m, totalSamples));
        } catch (Exception ex) {
            job.fail(ex.getMessage() != null ? ex.getMessage() : ex.toString());
        }
    }

    private ApproxResult finalize(Map<String, Double> weightedSum, Map<String, int[]> endpoints,
                                  long totalSamples, int batches, int m, int n) {
        List<EdgeEstimate> edges = new ArrayList<>(endpoints.size());
        for (Map.Entry<String, int[]> en : endpoints.entrySet()) {
            int[] uv = en.getValue();
            edges.add(new EdgeEstimate(uv[0], uv[1], round8(weightedSum.get(en.getKey()) / totalSamples)));
        }
        edges.sort((a, b) -> Double.compare(b.b(), a.b()));      // most-critical first

        List<EdgeEstimate> top = new ArrayList<>(edges.subList(0, Math.min(8, edges.size())));
        double finalEps = Bounds.achievedEpsilon(m, totalSamples, req.delta());
        var meta = new ApproxResult.Meta(totalSamples, batches, round6(finalEps), req.eps(),
                req.delta(), n, m, n);
        return new ApproxResult(edges, top, meta);
    }

    private String summary(int m, long totalSamples) {
        double eps = Bounds.achievedEpsilon(m, totalSamples, req.delta());
        String how = eps <= req.eps() ? "hit target ε" : "stopped at sample budget";
        return totalSamples + " sources · ε≈" + round6(eps) + " (" + how + ")";
    }

    private static double round8(double x) {
        return Math.round(x * 1e8) / 1e8;
    }

    private static double round6(double x) {
        return Math.round(x * 1e6) / 1e6;
    }
}

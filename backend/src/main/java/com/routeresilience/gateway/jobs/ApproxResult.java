package com.routeresilience.gateway.jobs;

import java.util.List;

/**
 * The finished estimate: every edge, the most-critical few, and the metadata that makes the
 * result defensible — how many sources it took, the ε actually achieved versus the target, and
 * how many sources exact Brandes would have needed (the cost the sampling avoided).
 */
public record ApproxResult(List<EdgeEstimate> edges, List<EdgeEstimate> top, Meta meta) {

    public record Meta(
            long samples, int batches,
            double epsilon, double targetEpsilon, double delta,
            int n, int m, int exactSources) {}
}

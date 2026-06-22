package com.routeresilience.gateway.jobs;

/** One segment's estimated normalized betweenness, ready to join with geometry client-side. */
public record EdgeEstimate(int u, int v, double b) {}

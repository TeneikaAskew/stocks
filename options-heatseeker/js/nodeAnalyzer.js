// ===== Node Analyzer =====

const NodeAnalyzer = {
    /**
     * Detect all nodes (King, Gatekeepers, Midpoints)
     */
    detectNodes(aggregatedStrikes, spotPrice) {
        // Filter strikes with significant gamma exposure
        const significantStrikes = aggregatedStrikes.filter(s =>
            Math.abs(s.net_gamma) >= CONFIG.NODES.MIN_THRESHOLD
        );

        if (significantStrikes.length === 0) {
            return { kingNode: null, gatekeepers: [], midpoints: [], allNodes: [] };
        }

        // Sort by absolute gamma (descending)
        const sortedByGamma = [...significantStrikes].sort((a, b) =>
            Math.abs(b.net_gamma) - Math.abs(a.net_gamma)
        );

        // King Node: Highest absolute gamma
        const kingNode = {
            type: 'king',
            strike: sortedByGamma[0].strike,
            gamma: sortedByGamma[0].net_gamma,
            distance_from_spot: sortedByGamma[0].strike - spotPrice,
            distance_percent: ((sortedByGamma[0].strike - spotPrice) / spotPrice) * 100
        };

        // Gatekeepers: Next highest nodes
        const gatekeepers = sortedByGamma
            .slice(1, CONFIG.NODES.TOP_NODES_COUNT)
            .map(s => ({
                type: 'gatekeeper',
                strike: s.strike,
                gamma: s.net_gamma,
                distance_from_spot: s.strike - spotPrice,
                distance_percent: ((s.strike - spotPrice) / spotPrice) * 100
            }));

        // Midpoints: Strikes between competing nodes
        const midpoints = this.detectMidpoints(sortedByGamma, spotPrice);

        // All nodes combined
        const allNodes = [kingNode, ...gatekeepers, ...midpoints];

        return {
            kingNode,
            gatekeepers,
            midpoints,
            allNodes
        };
    },

    /**
     * Detect midpoint zones (between competing high-value nodes)
     */
    detectMidpoints(sortedStrikes, spotPrice) {
        const midpoints = [];

        // Look for strikes between nodes with opposite gamma signs
        for (let i = 0; i < sortedStrikes.length - 1; i++) {
            const current = sortedStrikes[i];
            const next = sortedStrikes[i + 1];

            // Check if they have opposite signs and are both significant
            if (current.net_gamma * next.net_gamma < 0) {
                const gammaRatio = Math.abs(current.net_gamma / next.net_gamma);

                // If gamma values are similar (within threshold), it's a midpoint zone
                if (gammaRatio >= CONFIG.NODES.MIDPOINT_THRESHOLD &&
                    gammaRatio <= 1 / CONFIG.NODES.MIDPOINT_THRESHOLD) {

                    const midStrike = (current.strike + next.strike) / 2;

                    midpoints.push({
                        type: 'midpoint',
                        strike: midStrike,
                        lower_bound: Math.min(current.strike, next.strike),
                        upper_bound: Math.max(current.strike, next.strike),
                        gamma_1: current.net_gamma,
                        gamma_2: next.net_gamma,
                        distance_from_spot: midStrike - spotPrice,
                        distance_percent: ((midStrike - spotPrice) / spotPrice) * 100
                    });
                }
            }
        }

        return midpoints;
    },

    /**
     * Classify node strength based on retest count and time
     */
    classifyNodeStrength(node, priceHistory = []) {
        // First touch: strongest (100%)
        // Second touch: ~66% strength
        // Third+ touches: ~33% strength

        let retestCount = 0;

        for (const price of priceHistory) {
            const diff = Math.abs(price - node.strike);
            const threshold = node.strike * 0.002;  // 0.2% threshold

            if (diff <= threshold) {
                retestCount++;
            }
        }

        let strength = 1.0;  // Default: first touch
        if (retestCount >= 3) {
            strength = 0.33;
        } else if (retestCount === 2) {
            strength = 0.66;
        }

        return {
            ...node,
            retest_count: retestCount,
            strength,
            strength_label: strength >= 0.8 ? 'Strong' : strength >= 0.5 ? 'Medium' : 'Weak'
        };
    },

    /**
     * Detect hedge nodes (far from current price, typically for major events)
     */
    detectHedgeNodes(aggregatedStrikes, spotPrice, threshold = 0.10) {
        const hedgeNodes = [];

        for (const strike of aggregatedStrikes) {
            const distancePercent = Math.abs((strike.strike - spotPrice) / spotPrice);

            // Hedge nodes are far OTM (>10% away) with significant OI
            if (distancePercent > threshold &&
                Math.abs(strike.net_gamma) >= CONFIG.NODES.MIN_THRESHOLD) {

                hedgeNodes.push({
                    type: 'hedge',
                    strike: strike.strike,
                    gamma: strike.net_gamma,
                    distance_from_spot: strike.strike - spotPrice,
                    distance_percent: ((strike.strike - spotPrice) / spotPrice) * 100,
                    direction: strike.strike > spotPrice ? 'upside' : 'downside'
                });
            }
        }

        return hedgeNodes;
    },

    /**
     * Detect OPEX nodes (related to monthly expiration)
     */
    detectOPEXNodes(options, aggregatedStrikes) {
        // Find options expiring on next OPEX (monthly)
        const opexOptions = options.filter(o => {
            // Monthly OPEX is 3rd Friday of month
            const expDate = new Date(o.expiration);
            const dayOfMonth = expDate.getDate();
            const dayOfWeek = expDate.getDay();

            // Rough check for 3rd Friday (between 15-21 and Friday)
            return dayOfWeek === 5 && dayOfMonth >= 15 && dayOfMonth <= 21;
        });

        if (opexOptions.length === 0) return [];

        // Aggregate OPEX options by strike
        const opexStrikes = DataLoader.aggregateByStrike(opexOptions);

        // Filter significant OPEX strikes
        return opexStrikes
            .filter(s => Math.abs(s.net_gamma) >= CONFIG.NODES.MIN_THRESHOLD)
            .map(s => ({
                type: 'opex',
                strike: s.strike,
                gamma: s.net_gamma,
                expiration: opexOptions.find(o => o.strike === s.strike)?.expiration
            }));
    },

    /**
     * Calculate magnetic pull strength
     */
    calculateMagneticPull(strike, spotPrice, gamma) {
        const distance = Math.abs(strike - spotPrice);
        const distancePercent = distance / spotPrice;

        // Magnetic pull decreases with distance
        // Increases with gamma magnitude
        const pull = Math.abs(gamma) / (1 + distancePercent * 100);

        return {
            strike,
            pull_strength: pull,
            direction: strike > spotPrice ? 'up' : 'down',
            distance,
            distance_percent: distancePercent * 100
        };
    },

    /**
     * Detect accumulation vs dissipation
     */
    detectFlowPattern(currentStrikes, previousStrikes) {
        if (!previousStrikes || previousStrikes.length === 0) {
            return { pattern: 'unknown', changes: [] };
        }

        const changes = [];

        for (const current of currentStrikes) {
            const previous = previousStrikes.find(p => p.strike === current.strike);

            if (previous) {
                const gammaChange = current.net_gamma - previous.net_gamma;
                const changePercent = (gammaChange / previous.net_gamma) * 100;

                if (Math.abs(changePercent) > 10) {  // Significant change threshold
                    changes.push({
                        strike: current.strike,
                        gamma_change: gammaChange,
                        change_percent: changePercent,
                        pattern: gammaChange > 0 ? 'accumulation' : 'dissipation'
                    });
                }
            }
        }

        // Determine overall pattern
        const accumulationCount = changes.filter(c => c.pattern === 'accumulation').length;
        const dissipationCount = changes.filter(c => c.pattern === 'dissipation').length;

        let overallPattern = 'stable';
        if (accumulationCount > dissipationCount * 1.5) {
            overallPattern = 'accumulation';
        } else if (dissipationCount > accumulationCount * 1.5) {
            overallPattern = 'dissipation';
        }

        return {
            pattern: overallPattern,
            changes,
            accumulation_count: accumulationCount,
            dissipation_count: dissipationCount
        };
    },

    /**
     * Detect map reshuffle (significant change in dealer positioning)
     */
    detectReshuffle(currentNodes, previousNodes, threshold = 0.3) {
        if (!previousNodes || previousNodes.allNodes.length === 0) {
            return { reshuffled: false, changes: [] };
        }

        const changes = [];

        // Check if king node changed
        const kingChanged = currentNodes.kingNode.strike !== previousNodes.kingNode.strike;

        if (kingChanged) {
            changes.push({
                type: 'king_node_shift',
                from: previousNodes.kingNode.strike,
                to: currentNodes.kingNode.strike,
                significance: 'high'
            });
        }

        // Check for significant gamma changes at key strikes
        for (const currentNode of currentNodes.allNodes) {
            const previousNode = previousNodes.allNodes.find(n =>
                Math.abs(n.strike - currentNode.strike) < currentNode.strike * 0.01
            );

            if (previousNode) {
                const gammaChangePercent = Math.abs(
                    (currentNode.gamma - previousNode.gamma) / previousNode.gamma
                );

                if (gammaChangePercent > threshold) {
                    changes.push({
                        type: 'gamma_shift',
                        strike: currentNode.strike,
                        change_percent: gammaChangePercent * 100,
                        significance: gammaChangePercent > 0.5 ? 'high' : 'medium'
                    });
                }
            }
        }

        const reshuffled = kingChanged || changes.filter(c => c.significance === 'high').length > 1;

        return {
            reshuffled,
            changes,
            timestamp: new Date().toISOString()
        };
    }
};

// Freeze NodeAnalyzer to prevent modifications
Object.freeze(NodeAnalyzer);

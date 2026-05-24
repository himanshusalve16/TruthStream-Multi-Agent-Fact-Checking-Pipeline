import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { Activity } from 'lucide-react'
import type { ClaimVerdict } from '../context/JobContext'

interface Props {
  claims: Array<{ claim_id: string; text: string }>
  verdicts: ClaimVerdict[]
}

const VERDICT_COLORS: Record<string, string> = {
  SUPPORTED: '#10b981',    // Emerald
  REFUTED: '#ef4444',      // Rose
  CONTESTED: '#f59e0b',    // Amber
  UNVERIFIABLE: '#64748b', // Slate
}

export default function VerdictTimeline({ claims, verdicts }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current || claims.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = svgRef.current.clientWidth || 700
    const nodeR = 24
    const margin = 48
    const spacing = Math.min(120, (width - margin * 2) / Math.max(claims.length - 1, 1))
    const totalW = margin * 2 + spacing * (claims.length - 1)
    const height = 150

    svg
      .attr('width', Math.max(width, totalW))
      .attr('height', height)

    const verdictMap = Object.fromEntries(verdicts.map((v) => [v.claim_id, v]))

    const nodes = claims.map((c, i) => ({
      ...c,
      x: margin + i * spacing,
      y: height / 2,
      verdict: verdictMap[c.claim_id],
    }))

    const g = svg.append('g')

    // Add glowing filter for timeline nodes
    const defs = svg.append('defs')
    Object.keys(VERDICT_COLORS).forEach((key) => {
      const filter = defs.append('filter')
        .attr('id', `node-glow-${key}`)
        .attr('x', '-50%')
        .attr('y', '-50%')
        .attr('width', '200%')
        .attr('height', '200%')

      filter.append('feGaussianBlur')
        .attr('stdDeviation', '4')
        .attr('result', 'blur')

      filter.append('feMerge')
        .selectAll('feMergeNode')
        .data(['blur', 'SourceGraphic'])
        .enter()
        .append('feMergeNode')
        .attr('in', (d) => d)
    })

    // Draw connecting paths (bridges) between claim nodes
    if (nodes.length > 1) {
      g.selectAll('line')
        .data(nodes.slice(0, -1))
        .enter()
        .append('line')
        .attr('x1', (d) => d.x + nodeR)
        .attr('y1', (d) => d.y)
        .attr('x2', (_, i) => nodes[i + 1].x - nodeR)
        .attr('y2', (d) => d.y)
        .attr('stroke', 'rgba(99, 102, 241, 0.15)')
        .attr('stroke-width', 2)
        .attr('stroke-dasharray', '4 4')
    }

    // Draw nodes groups
    const nodeGroups = g.selectAll('g.node')
      .data(nodes)
      .enter()
      .append('g')
      .attr('class', 'node')
      .attr('transform', (d) => `translate(${d.x}, ${d.y})`)
      .style('cursor', 'pointer')

    // Outer glow highlight circle
    nodeGroups.append('circle')
      .attr('r', nodeR + 6)
      .attr('fill', (d) => d.verdict ? VERDICT_COLORS[d.verdict.verdict] + '0f' : 'transparent')
      .attr('stroke', (d) => d.verdict ? VERDICT_COLORS[d.verdict.verdict] + '1a' : 'transparent')
      .attr('stroke-width', 1.5)

    // Inner main colored circle
    nodeGroups.append('circle')
      .attr('r', 0)
      .attr('fill', (d) => d.verdict ? VERDICT_COLORS[d.verdict.verdict] : '#1f2937')
      .attr('stroke', (d) => d.verdict ? VERDICT_COLORS[d.verdict.verdict] : 'rgba(99, 102, 241, 0.3)')
      .attr('stroke-width', 2)
      .attr('filter', (d) => d.verdict ? `url(#node-glow-${d.verdict.verdict})` : 'none')
      .transition()
      .delay((_, i) => i * 150)
      .duration(500)
      .ease(d3.easeBackOut)
      .attr('r', nodeR)

    // Confidence percentile text inside circle
    nodeGroups.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', '#ffffff')
      .attr('font-size', 10)
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('font-weight', '700')
      .text((d) => d.verdict ? `${Math.round(d.verdict.confidence * 100)}%` : '…')

    // Claim number tag text below node
    nodeGroups.append('text')
      .attr('y', nodeR + 18)
      .attr('text-anchor', 'middle')
      .attr('fill', '#9ca3af')
      .attr('font-size', 10)
      .attr('font-weight', '600')
      .attr('font-family', 'Inter, sans-serif')
      .text((_, i) => `#0${i + 1}`)

    // Verdict label above node
    nodeGroups.append('text')
      .attr('y', -(nodeR + 14))
      .attr('text-anchor', 'middle')
      .attr('fill', (d) => d.verdict ? VERDICT_COLORS[d.verdict.verdict] : '#6b7280')
      .attr('font-size', 9)
      .attr('font-family', 'Inter, sans-serif')
      .attr('font-weight', '700')
      .attr('letter-spacing', '0.05em')
      .text((d) => d.verdict ? d.verdict.verdict : 'ANALYZING')

    // Interactive tooltip details
    nodeGroups
      .append('title')
      .text((d) => `${d.text}\n\nStatus: ${d.verdict ? d.verdict.verdict : 'Pending verification'}`)

  }, [claims, verdicts])

  if (claims.length === 0) return null

  return (
    <section id="verdict-timeline" className="mb-6 text-left">
      <h3 className="text-xs font-bold text-text-dim uppercase tracking-wider mb-3 flex items-center gap-1.5">
        <Activity size={13} className="text-accent" /> claim consensus stream
      </h3>
      <div className="glass-card p-6 overflow-x-auto bg-bg-glass backdrop-blur-xl border border-border rounded-2xl shadow-card scrollbar">
        <svg ref={svgRef} className="mx-auto block" style={{ minWidth: `${claims.length * 90}px` }} />
      </div>
    </section>
  )
}

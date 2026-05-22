import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { ClaimVerdict } from '../context/JobContext'

interface Props {
  claims: Array<{ claim_id: string; text: string }>
  verdicts: ClaimVerdict[]
}

const VERDICT_COLORS: Record<string, string> = {
  SUPPORTED: '#22c55e',
  REFUTED: '#ef4444',
  CONTESTED: '#f59e0b',
  UNVERIFIABLE: '#6b7fa3',
}

export default function VerdictTimeline({ claims, verdicts }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current || claims.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = svgRef.current.clientWidth || 600
    const nodeR = 22
    const margin = 40
    const spacing = Math.min(100, (width - margin * 2) / Math.max(claims.length - 1, 1))
    const totalW = margin * 2 + spacing * (claims.length - 1)
    const height = 140

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

    // Draw connecting lines
    if (nodes.length > 1) {
      g.selectAll('line')
        .data(nodes.slice(0, -1))
        .enter()
        .append('line')
        .attr('x1', (d) => d.x + nodeR)
        .attr('y1', (d) => d.y)
        .attr('x2', (_, i) => nodes[i + 1].x - nodeR)
        .attr('y2', (d) => d.y)
        .attr('stroke', 'rgba(99,120,180,0.25)')
        .attr('stroke-width', 2)
        .attr('stroke-dasharray', '4 4')
    }

    // Draw nodes
    const nodeGroups = g.selectAll('g.node')
      .data(nodes)
      .enter()
      .append('g')
      .attr('class', 'node')
      .attr('transform', (d) => `translate(${d.x}, ${d.y})`)
      .style('cursor', 'pointer')

    // Outer glow circle
    nodeGroups.append('circle')
      .attr('r', nodeR + 6)
      .attr('fill', (d) => d.verdict ? VERDICT_COLORS[d.verdict.verdict] + '22' : 'transparent')

    // Main circle
    nodeGroups.append('circle')
      .attr('r', 0)
      .attr('fill', (d) => d.verdict ? VERDICT_COLORS[d.verdict.verdict] : 'rgba(99,120,180,.3)')
      .attr('stroke', (d) => d.verdict ? VERDICT_COLORS[d.verdict.verdict] : 'rgba(99,120,180,.5)')
      .attr('stroke-width', 2)
      .transition()
      .delay((_, i) => i * 120)
      .duration(400)
      .ease(d3.easeBackOut)
      .attr('r', nodeR)

    // Confidence text inside node
    nodeGroups.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', '#fff')
      .attr('font-size', 10)
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('font-weight', '600')
      .text((d) => d.verdict ? `${Math.round(d.verdict.confidence * 100)}%` : '…')

    // Claim number below
    nodeGroups.append('text')
      .attr('y', nodeR + 16)
      .attr('text-anchor', 'middle')
      .attr('fill', '#6b7fa3')
      .attr('font-size', 10)
      .attr('font-family', 'Inter, sans-serif')
      .text((_, i) => `#${i + 1}`)

    // Verdict label above
    nodeGroups.append('text')
      .attr('y', -(nodeR + 12))
      .attr('text-anchor', 'middle')
      .attr('fill', (d) => d.verdict ? VERDICT_COLORS[d.verdict.verdict] : '#6b7fa3')
      .attr('font-size', 9)
      .attr('font-family', 'Inter, sans-serif')
      .attr('font-weight', '600')
      .text((d) => d.verdict ? d.verdict.verdict : '')

    // Tooltip on hover
    nodeGroups
      .append('title')
      .text((d) => d.text.slice(0, 80) + (d.text.length > 80 ? '…' : ''))

  }, [claims, verdicts])

  if (claims.length === 0) return null

  return (
    <section id="verdict-timeline" style={{ marginBottom: '24px' }}>
      <h2 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '12px' }}>
        📊 Claim Verdict Timeline
      </h2>
      <div className="glass-card" style={{ padding: '16px', overflowX: 'auto' }}>
        <svg ref={svgRef} style={{ width: '100%', display: 'block', minWidth: `${claims.length * 80}px` }} />
      </div>
    </section>
  )
}

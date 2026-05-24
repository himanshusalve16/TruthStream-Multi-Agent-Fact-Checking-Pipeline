import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

interface Props {
  confidence: number  // 0.0 to 1.0
  verdict: string
  size?: number
}

const VERDICT_COLORS: Record<string, string> = {
  MOSTLY_TRUE: '#10b981', // Emerald
  MIXTURE: '#f59e0b',     // Amber
  MOSTLY_FALSE: '#ef4444', // Rose
  UNVERIFIABLE: '#64748b', // Slate
}

export default function ConfidenceGauge({ confidence, verdict, size = 180 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const r = size / 2
    const innerR = r * 0.70
    const arcAngle = Math.PI * 0.72  // Arch opening angle
    const color = VERDICT_COLORS[verdict] || '#64748b'

    const arcGenerator = d3.arc<{ startAngle: number; endAngle: number }>()
      .innerRadius(innerR)
      .outerRadius(r - 5)
      .cornerRadius(6)

    // Set SVG sizing
    svg
      .attr('width', size)
      .attr('height', size * 0.75)

    // Add filters & gradients inside defs
    const defs = svg.append('defs')

    // Drop shadow filter for glow effect
    const filter = defs.append('filter')
      .attr('id', `glow-${verdict}`)
      .attr('x', '-20%')
      .attr('y', '-20%')
      .attr('width', '140%')
      .attr('height', '140%')

    filter.append('feGaussianBlur')
      .attr('stdDeviation', '4')
      .attr('result', 'blur')

    filter.append('feMerge')
      .selectAll('feMergeNode')
      .data(['blur', 'SourceGraphic'])
      .enter()
      .append('feMergeNode')
      .attr('in', (d) => d)

    // Linear gradient for progress arc
    const gradient = defs.append('linearGradient')
      .attr('id', `gradient-${verdict}`)
      .attr('x1', '0%')
      .attr('y1', '100%')
      .attr('x2', '100%')
      .attr('y2', '0%')

    gradient.append('stop')
      .attr('offset', '0%')
      .attr('stop-color', color)
      .attr('stop-opacity', '0.6')

    gradient.append('stop')
      .attr('offset', '100%')
      .attr('stop-color', color)
      .attr('stop-opacity', '1')

    const g = svg
      .append('g')
      .attr('transform', `translate(${r}, ${r * 0.95})`)

    // Background track arc
    g.append('path')
      .datum({ startAngle: -arcAngle, endAngle: arcAngle })
      .attr('d', arcGenerator as any)
      .attr('fill', 'rgba(255, 255, 255, 0.03)')
      .attr('stroke', 'rgba(255, 255, 255, 0.02)')
      .attr('stroke-width', '1')

    // Value progress arc
    const filled = -arcAngle + confidence * 2 * arcAngle
    g.append('path')
      .datum({ startAngle: -arcAngle, endAngle: -arcAngle })
      .attr('d', arcGenerator as any)
      .attr('fill', `url(#gradient-${verdict})`)
      .attr('filter', `url(#glow-${verdict})`)
      .transition()
      .duration(1200)
      .ease(d3.easeCubicOut)
      .attrTween('d', function () {
        const interpolate = d3.interpolate(-arcAngle, filled)
        return function (t) {
          return arcGenerator({ startAngle: -arcAngle, endAngle: interpolate(t) } as any) || ''
        }
      })

    // Center percentage text
    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('y', -12)
      .attr('fill', '#ffffff')
      .attr('font-size', size * 0.19)
      .attr('font-weight', '800')
      .attr('font-family', 'JetBrains Mono, monospace')
      .text(`${Math.round(confidence * 100)}%`)

    // Verdict metric label
    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('y', size * 0.12)
      .attr('fill', '#9ca3af')
      .attr('font-size', size * 0.075)
      .attr('font-weight', '600')
      .attr('font-family', 'Inter, sans-serif')
      .attr('letter-spacing', '0.05em')
      .text('CONFIDENCE')

    // Min label
    g.append('text')
      .attr('x', -(r * 0.8))
      .attr('y', r * 0.3)
      .attr('fill', '#4b5563')
      .attr('font-size', size * 0.065)
      .attr('font-weight', '600')
      .attr('font-family', 'JetBrains Mono, monospace')
      .text('0%')

    // Max label
    g.append('text')
      .attr('x', r * 0.7)
      .attr('y', r * 0.3)
      .attr('fill', '#4b5563')
      .attr('font-size', size * 0.065)
      .attr('font-weight', '600')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('text-anchor', 'end')
      .text('100%')

  }, [confidence, verdict, size])

  return <svg ref={svgRef} id="confidence-gauge" className="mx-auto" />
}

import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

interface Props {
  confidence: number  // 0.0 to 1.0
  verdict: string
  size?: number
}

const VERDICT_COLORS: Record<string, string> = {
  MOSTLY_TRUE: '#22c55e',
  MIXTURE: '#f59e0b',
  MOSTLY_FALSE: '#ef4444',
  UNVERIFIABLE: '#6b7fa3',
}

export default function ConfidenceGauge({ confidence, verdict, size = 200 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const r = size / 2
    const innerR = r * 0.65
    const arcAngle = Math.PI * 0.75  // 135 degrees each side
    const color = VERDICT_COLORS[verdict] || '#6b7fa3'

    const arcGenerator = d3.arc<{ startAngle: number; endAngle: number }>()
      .innerRadius(innerR)
      .outerRadius(r - 4)
      .cornerRadius(4)

    const g = svg
      .attr('width', size)
      .attr('height', size * 0.7)
      .append('g')
      .attr('transform', `translate(${r}, ${r * 0.95})`)

    // Background arc (track)
    g.append('path')
      .datum({ startAngle: -arcAngle, endAngle: arcAngle })
      .attr('d', arcGenerator as any)
      .attr('fill', 'rgba(255,255,255,0.06)')

    // Value arc
    const filled = -arcAngle + confidence * 2 * arcAngle
    g.append('path')
      .datum({ startAngle: -arcAngle, endAngle: -arcAngle })
      .attr('d', arcGenerator as any)
      .attr('fill', color)
      .attr('filter', `drop-shadow(0 0 8px ${color}80)`)
      .transition()
      .duration(900)
      .ease(d3.easeCubicOut)
      .attrTween('d', function () {
        const interpolate = d3.interpolate(-arcAngle, filled)
        return function (t) {
          return arcGenerator({ startAngle: -arcAngle, endAngle: interpolate(t) } as any) || ''
        }
      })

    // Center text - percentage
    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('y', -10)
      .attr('fill', color)
      .attr('font-size', size * 0.18)
      .attr('font-weight', '800')
      .attr('font-family', 'JetBrains Mono, monospace')
      .text(`${Math.round(confidence * 100)}%`)

    // Verdict label
    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('y', size * 0.1)
      .attr('fill', '#8898bc')
      .attr('font-size', size * 0.075)
      .attr('font-family', 'Inter, sans-serif')
      .text('Confidence')

    // Min/Max labels
    g.append('text')
      .attr('x', -(r * 0.85))
      .attr('y', 16)
      .attr('fill', '#6b7fa3')
      .attr('font-size', size * 0.065)
      .attr('font-family', 'JetBrains Mono, monospace')
      .text('0%')

    g.append('text')
      .attr('x', r * 0.75)
      .attr('y', 16)
      .attr('fill', '#6b7fa3')
      .attr('font-size', size * 0.065)
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('text-anchor', 'end')
      .text('100%')

  }, [confidence, verdict, size])

  return <svg ref={svgRef} id="confidence-gauge" />
}

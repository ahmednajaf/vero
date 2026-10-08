// Evil Charts' Hatched Multiple Bar Chart on 21st.dev, MIT (see notices).
import type { SVGProps } from "react";

export function HatchedBarPattern({id, color}: {id: string; color: string}) {
  return <pattern id={id} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><rect width="5" height="5" opacity={.18} fill={color}/><rect width="1.5" height="5" fill={color}/></pattern>;
}
export function HatchedBar({patternId, ...props}: SVGProps<SVGRectElement> & {patternId?: string}) {
  const {x, y, width, height, fill} = props;
  // Missing values have no rectangle. A genuine zero stays zero-height.
  if (![x, y, width, height].every(value => typeof value === "number" && Number.isFinite(value))) return null;
  return <rect rx={3} x={x} y={y} width={width} height={height} stroke="none" fill={patternId ? `url(#${patternId})` : fill}/>;
}

// Specs card, from car_specs (the tool's artifact). The official specs of one catalog car, each
// with its source; or "no official data" with the importer link.
import { FullSpecs, ImporterLink, SourceLine, SpecTags } from './RankingCard'
import { Card, T } from './ui'

export default function SpecsCard({ result }) {
  const { card } = result
  return (
    <Card label="מפרט הרכב">
      <T weight={800} size={18}>{card.car}</T>
      {card.message ? <T size={14} muted>{card.message}</T> : null}
      <SpecTags specs={card.specs} />
      <FullSpecs specs={card.specs} open />
      <SourceLine sources={card.sources} />
      <ImporterLink url={card.importer_url} />
    </Card>
  )
}

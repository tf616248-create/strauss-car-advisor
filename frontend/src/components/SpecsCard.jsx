// Specs card, from car_specs (the tool's artifact). The official specs of one catalog car, each
// with its source; or "no official data" with the importer link.
import { FullSpecs, ImporterLink, SourceLine, SpecTags } from './RankingCard'

export default function SpecsCard({ result }) {
  const { card } = result
  return (
    <section className="card specs-card" aria-label="מפרט הרכב">
      <h3>{card.car}</h3>
      {card.message && <p className="hint">{card.message}</p>}
      <SpecTags specs={card.specs} />
      <FullSpecs specs={card.specs} open />
      <SourceLine sources={card.sources} />
      <ImporterLink url={card.importer_url} />
    </section>
  )
}

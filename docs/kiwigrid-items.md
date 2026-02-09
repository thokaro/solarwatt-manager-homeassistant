# Kiwigrid elements (from JSON)

| Label (from JSON) | Example Item Name | English Description | German Description |
|---|---|---|---|
| PowerBuffered | `kiwigrid_harmonized_power_buffered` | Power flow into the storage system | Leistungsfluss in das Speichersystem |
| PowerBufferedFromGrid | `kiwigrid_harmonized_power_buffered_from_grid` | Power buffered into storage from the grid | Laden in den Speicher aus dem Netz (Leistung) |
| PowerBufferedFromProducers | `kiwigrid_harmonized_power_buffered_from_producers` | Power buffered into storage from producers | Laden in den Speicher von Erzeugern (Leistung) |
| PowerConsumed | `kiwigrid_harmonized_power_consumed` | Total power consumed. All inner and outer consumers. | Gesamtverbrauch (Leistung). Alle inneren und äußeren Verbraucher. |
| PowerConsumedFromGrid | `kiwigrid_harmonized_power_consumed_from_grid` | Power consumed from the grid | Leistung aus dem Netz (Verbrauch) |
| PowerConsumedFromProducers | `kiwigrid_harmonized_power_consumed_from_producers` | Power consumed from producers | Leistung aus Erzeugern (Verbrauch) |
| PowerConsumedFromStorage | `kiwigrid_harmonized_power_consumed_from_storage` | Power consumed from storage | Leistung aus dem Speicher (Verbrauch) |
| #power_in | `kiwigrid_harmonized_power_in` | Metered power flowing into the consumer | Gemessene Leistung, die in den Verbraucher fließt |
| #power_out | `kiwigrid_harmonized_power_out` | Power delivered to the grid | Leistung ins Netz (Einspeisung) |
| PowerOutFromProducers | `kiwigrid_harmonized_power_out_from_producers` | Power exported to the grid from producers | Leistung ins Netz (Einspeisung) von Erzeugern |
| PowerOutFromStorage | `kiwigrid_harmonized_power_out_from_storage` | Power exported to the grid from storage | Leistung ins Netz (Einspeisung) aus dem Speicher |
| PowerProduced | `kiwigrid_harmonized_power_produced` | Power produced by the PV | Leistung erzeugt durch PV |
| PowerReleased | `kiwigrid_harmonized_power_released` | Power released | Freigesetzte Leistung |
| PowerSelfConsumed | `kiwigrid_harmonized_power_self_consumed` | Power consumed direct from PV plus energy stored | Leistung, die direkt aus PV verbraucht wird, plus in den Speicher geladene Leistung |
| PowerSelfSupplied | `kiwigrid_harmonized_power_self_supplied` | Power consumed direct from PV plus energy consumed from storage | Leistung, die direkt aus PV verbraucht wird, plus Leistung aus dem Speicher |
| #work | `kiwigrid_harmonized_work` | Energy | Energie: work |
| WorkBufferedFromGrid | `kiwigrid_harmonized_work_buffered_from_grid_total` | Energy buffered into storage from the grid (total / cumulative) | Laden in den Speicher aus dem Netz (Energie) (gesamt / kumulativ) |
| | `kiwigrid_harmonized_work_buffered_from_producers` | Energy buffered into storage from producers | Laden in den Speicher von Erzeugern (Energie) |
| WorkBufferedFromProducers | `kiwigrid_harmonized_work_buffered_from_producers_total` | Energy buffered into storage from producers (total / cumulative) | Laden in den Speicher von Erzeugern (Energie) (gesamt / kumulativ) |
| WorkBuffered | `kiwigrid_harmonized_work_buffered_total` | Energy flow into the storage system (total / cumulative) | Energiefluss in das Speichersystem (gesamt / kumulativ) |
| WorkConsumedFromGrid | `kiwigrid_harmonized_work_consumed_from_grid_total` | Energy consumed from the grid (total / cumulative) | Energie aus dem Netz (Verbrauch) (gesamt / kumulativ) |
| | `kiwigrid_harmonized_work_consumed_from_producers` | Energy consumed from producers | Energie aus Erzeugern (Verbrauch) |
| WorkConsumedFromProducers | `kiwigrid_harmonized_work_consumed_from_producers_total` | Energy consumed from producers (total / cumulative) | Energie aus Erzeugern (Verbrauch) (gesamt / kumulativ) |
| WorkConsumedFromStorage | `kiwigrid_harmonized_work_consumed_from_storage_total` | Energy consumed from storage (total / cumulative) | Energie aus dem Speicher (Verbrauch) (gesamt / kumulativ) |
| WorkConsumed | `kiwigrid_harmonized_work_consumed_total` | Total energy consumed. All inner and outer consumers (total / cumulative) | Gesamtverbrauch (Energie). Alle inneren und äußeren Verbraucher (gesamt / kumulativ) |
| Throttled Energy | `kiwigrid_harmonized_work_in_session` | Energy consumed during current/last charging session | Energieverbrauch der aktuellen/letzten Ladesession |
| WorkIn | `kiwigrid_harmonized_work_in_total` | Metered energy flowing into the consumer (total / cumulative) | Gemessene Energie, die in den Verbraucher fließt (gesamt / kumulativ) |
| #work_in_total_extrapolated | `kiwigrid_harmonized_work_in_total_extrapolated` | Metered energy flowing into the consumer total extrapolated | Gemessene Energie, die in den Verbraucher fließt, total extrapoliert |
| #work_out | `kiwigrid_harmonized_work_out` | Energy delivered to the grid | Energie ins Netz (Einspeisung) |
| WorkOutFromProducers | `kiwigrid_harmonized_work_out_from_producers_total` | Energy exported to the grid from producers (total / cumulative) | Energie ins Netz (Einspeisung) von Erzeugern (gesamt / kumulativ) |
| WorkOutFromStorage | `kiwigrid_harmonized_work_out_from_storage_total` | Energy exported to the grid from storage (total / cumulative) | Energie ins Netz (Einspeisung) aus dem Speicher (gesamt / kumulativ) |
| WorkOut | `kiwigrid_harmonized_work_out_total` | Energy delivered to the grid (total / cumulative) | Energie ins Netz (Einspeisung) (gesamt / kumulativ) |
| #work_out_total_extrapolated | `kiwigrid_harmonized_work_out_total_extrapolated` | Energy delivered to the grid total extrapolated | Energie ins Netz (Einspeisung) total extrapoliert |
| WorkProduced | `kiwigrid_harmonized_work_produced_total` | Energy produced by the PV (total / cumulative) | Energie erzeugt durch PV (gesamt / kumulativ) |
| WorkReleased | `kiwigrid_harmonized_work_released_total` | Energy released (total / cumulative) | Freigesetzte Energie (gesamt / kumulativ) |
| WorkSelfConsumed | `kiwigrid_harmonized_work_self_consumed_total` | Energy consumed direct from PV plus energy stored (total / cumulative) | Energie, die direkt aus PV verbraucht wird, plus in den Speicher geladene Energie (gesamt / kumulativ) |
| WorkSelfSupplied | `kiwigrid_harmonized_work_self_supplied_total` | Energy consumed direct from PV plus energy consumed from storage (total / cumulative) | Energie, die direkt aus PV verbraucht wird, plus aus dem Speicher entnommene Energie (gesamt / kumulativ) |
| #work_total | `kiwigrid_harmonized_work_total` | Energy (total / cumulative) | Energie: work (gesamt / kumulativ) |

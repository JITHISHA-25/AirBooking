// Keep stored records intact while omitting legacy sample markers in the UI.
export function mealLabel(value) {
  return String(value ?? '').replace(/\bdemo\b[ \t]*/gi, '').replace(/[ \t]{2,}/g, ' ').trim()
}

export function statusSourceLabel(source) {
  return String(source || '').toLowerCase() === 'airlabs' ? 'AirLabs live' : 'AirBooking stored status'
}

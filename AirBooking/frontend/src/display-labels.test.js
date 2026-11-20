import assert from 'node:assert/strict'
import test from 'node:test'
import { mealLabel, statusSourceLabel } from './display-labels.js'

test('legacy status sources remain clearly labeled as stored data', () => {
  for (const source of ['demo', 'Demo', 'airbooking', 'AirBooking', undefined]) {
    assert.equal(statusSourceLabel(source), 'AirBooking stored status')
  }
  assert.equal(statusSourceLabel('airlabs'), 'AirLabs live')
  assert.equal(statusSourceLabel('AirLabs'), 'AirLabs live')
})

test('meal labels omit sample markers without changing stored values', () => {
  const original = 'Demo vegetable biryani'
  assert.equal(mealLabel(original), 'vegetable biryani')
  assert.equal(original, 'Demo vegetable biryani')
  assert.equal(mealLabel('Browser demo fruit box'), 'Browser fruit box')
  assert.equal(mealLabel('DEMO chicken rice'), 'chicken rice')
  assert.equal(mealLabel('Chicken with rice. Demo catalog update.'), 'Chicken with rice. catalog update.')
  assert.equal(mealLabel('Demography special'), 'Demography special')
  assert.equal(mealLabel(undefined), '')
})

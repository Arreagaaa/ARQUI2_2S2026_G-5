import { test, expect } from '@playwright/test'

const BASE_URL = process.env.PORTUS_BASE_URL || 'http://127.0.0.1:5000'

async function login(page, username, password) {
  await page.goto(`${BASE_URL}/login`)
  await page.getByPlaceholder('operador1').fill(username)
  await page.getByPlaceholder('********').fill(password)
  await page.getByRole('button', { name: 'Ingresar' }).click()
}

test('TERMINAL navega sus pestanas obligatorias', async ({ page }) => {
  await login(page, 'operador1', 'terminal123')
  await expect(page).toHaveURL(/\/terminal\/operacion/)
  await expect(page.getByText('Operacion', { exact: true }).first()).toBeVisible()

  for (const tab of ['Turnos', 'Retenciones', 'Patio', 'Grua', 'Alarmas', 'Citas', 'Reportes']) {
    await page.getByRole('link', { name: new RegExp(tab) }).click()
    await expect(page.getByText(tab, { exact: false }).first()).toBeVisible()
  }
})

test('NAVIERA carga catalogos para crear manifiesto', async ({ page }) => {
  await login(page, 'maersk', 'maersk123')
  await expect(page).toHaveURL(/\/naviera\/manifiestos/)
  await page.getByRole('button', { name: /Nuevo manifiesto/ }).click()

  const transportista = page.locator('select').filter({ has: page.locator('option[value="trans_rapido"]') })
  await expect(transportista).toHaveCount(1)
  await expect(page.locator('#catalogo-contenedores option')).not.toHaveCount(0)
})

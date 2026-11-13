# Revisão da placa — 2026-11-12

Revisão de `teclado.kicad_pcb` (versão com módulo Black Pill em soquete, switches com modelo 3D).
Nenhum erro elétrico encontrado. A placa não foi alterada na revisão.

## Conferido e OK

- DRC: 0 curto, 0 isolamento, 0 ligação aberta. 316 avisos de serigrafia (texto sobre pad/borda), cosméticos.
- ERC e paridade esquema ↔ placa: só avisos cosméticos (fora da grade, campo `Sim.Device`, símbolo `SW_stab`).
- Matriz: 76 teclas em 76 posições únicas, 6 linhas × 14 colunas. Diodos todos no mesmo sentido
  (catodo na linha), o do knob (D101) inclusive. Clique do knob em ROW0 × COL13, posição livre.
- Layout bate com `layout/teclado-kle.json`. Estabilizadores em Backspace, Enter e Espaço.
- LEDs: 102 em cadeia única (LED1–76 teclas → LED101–114 underglow → LED201–212 laterais), um capacitor
  ao lado de cada um, laterais apontando para fora da placa.
- Black Pill: pinagem do símbolo confere com o módulo WeAct (conferido de memória, não contra o desenho
  do fabricante). PA8 (RGB), PB6/PB7 (I2C) e PA0/PA1 (knob) servem para o QMK.
- USB-C: resistores de CC de 5,1k, ESD e fusível certos; boca 0,2 mm para fora da borda.

## Pendências antes de fabricar

1. **OLED: ordem dos pinos.** O header J3 está GND-VCC-SCL-SDA de cima para baixo, com o módulo deitado
   para a direita. Se o módulo comprado tiver a ordem invertida, ele cai para a esquerda, em cima do USB-C.
   Conferir com o módulo na mão; se precisar, inverter por script.
2. **LED lateral (footprint feito à mão, `teclado.pretty`).** As funções dos pinos batem com o datasheet
   OPSCO SK6812SIDE-A-012 rev B/2 (1 DIN, 2 VDD, 3 DOUT, 4 GND). O lado físico (espelhamento) não foi
   confirmado pelo desenho. Se estiver espelhado, só os 12 laterais falham: são os últimos da cadeia.

## Obrigatório no firmware e na montagem

3. **Corrente dos LEDs × fusível de 500 mA.** 102 LEDs em branco total puxam ~3,7 A. O QMK precisa limitar
   o brilho (~10% em branco, ~30% em efeito colorido). Sem limite, o fusível abre ou a porta USB cai.
4. **Black Pill no verso.**
   - Soquete + módulo ocupam ~12–14 mm abaixo da placa (estimativa): o case precisa dessa folga.
   - Os botões BOOT0/NRST ficam virados para baixo: fazer a primeira gravação antes de fechar o case.
   - Nunca ligar o USB do módulo e o da placa ao mesmo tempo (mesmas linhas de dados).

## Menores

- Abas metálicas do knob (pads MP) sem ligação ao GND. Funciona igual.
- Trilhas de +5V de 0,3–0,5 mm servem para 500 mA. Se trocar o fusível por um maior, rever.

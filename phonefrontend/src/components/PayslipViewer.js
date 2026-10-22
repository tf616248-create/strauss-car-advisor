// The payslip, large: full screen with a big ✕ (56), like the website on a phone. Android's Back
// closes it too (onRequestClose). A screen reader stays inside it (accessibilityViewIsModal).
import { Image, Modal, Pressable, View } from 'react-native'
import { useColors } from '../theme'
import { T } from './ui'
import cfg from '../config/payslip.json'

const PT = cfg.texts

export default function PayslipViewer({ source, onClose }) {
  const c = useColors()
  return (
    <Modal visible animationType="fade" onRequestClose={onClose} statusBarTranslucent>
      <View accessibilityViewIsModal accessibilityLabel={PT.viewer} style={{ flex: 1, backgroundColor: '#000', direction: 'rtl' }}>
        <Pressable accessibilityRole="button" accessibilityLabel={PT.close} onPress={onClose}
          style={{ position: 'absolute', top: 24, right: 16, zIndex: 1, width: 56, height: 56, borderRadius: 28, backgroundColor: c.bg, alignItems: 'center', justifyContent: 'center' }}>
          <T size={26} weight={800}>✕</T>
        </Pressable>
        <Image testID="payslip-large" source={source} accessibilityLabel={PT.image} resizeMode="contain" style={{ flex: 1 }} />
      </View>
    </Modal>
  )
}

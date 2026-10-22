// Kobi's answer: Markdown, and one link only - the employee's profile ("כאן"), like the website.
import { render, screen, fireEvent } from '@testing-library/react-native'
import Answer from '@/components/Answer'
const P = require('@/config/profile.json').texts

test('/profile, bare or as a link\'s text, reads "כאן", named "כאן – פתיחת הפרופיל", and opens the profile', async () => {
  const onProfile = jest.fn()
  await render(<Answer text={'מלאו בפרופיל, /profile. או [/profile](/profile). או [כאן](/profile).'} onProfile={onProfile} />)
  const links = screen.getAllByRole('link')
  expect(links).toHaveLength(3)
  for (const l of links) expect(l.props.accessibilityLabel).toBe(P.linkLabel.replace('{text}', P.linkText))
  expect(screen.queryByText('/profile')).toBeNull()
  await fireEvent.press(links[0])
  expect(onProfile).toHaveBeenCalledTimes(1)
})

test('another Hebrew text for the link keeps its words in the name', async () => {
  await render(<Answer text={'[בפרופיל](/profile)'} onProfile={() => {}} />)
  expect(screen.getByRole('link').props.accessibilityLabel).toBe('בפרופיל – פתיחת הפרופיל')
})

test('any other link stays text; without onProfile there is no link', async () => {
  const { unmount } = await render(<Answer text={'[קישור](https://evil.example) ו-![](https://evil.example/i.png)'} onProfile={() => {}} />)
  expect(screen.queryAllByRole('link')).toHaveLength(0)
  expect(screen.getByText(/קישור/)).toBeTruthy()
  await unmount()
  await render(<Answer text={'בפרופיל: /profile'} />)
  expect(screen.queryAllByRole('link')).toHaveLength(0)
})
